"""
Planner node: classifies user intent and routes to the appropriate flow.

Routes:
  qa         — user wants an answer to a question about study materials
  self_check — user wants to test their knowledge on a topic
  clarify    — intent is ambiguous, ask a follow-up question
"""
import json
import re
from dataclasses import dataclass

from atlas.core.logging import logger
from atlas.llm.client import llm_client


@dataclass
class PlannerDecision:
    route: str                   # "qa" | "self_check" | "clarify"
    topic: str | None            # extracted topic for self_check
    clarify_message: str | None  # question to ask user when route == clarify


_SYSTEM_PROMPT = """You are a routing assistant for ATLAS, a PhD exam preparation system.

Classify the user's message into one of three routes:
- "qa"         — the user wants a factual or conceptual answer about study materials
- "self_check" — the user wants to test their knowledge on a topic
                 (signals: "проверь меня", "тест по", "самопроверка", "quiz", "test me", "check my knowledge on", etc.)
- "clarify"    — the intent is ambiguous and a follow-up question is needed

Rules:
- For "self_check" extract the topic from the message (string, in the original language).
- For "clarify" write a short clarifying question in the same language as the user's message.
- Default to "qa" when uncertain between "qa" and something else.
- If a previous user message is given, the current message may be a follow-up to it
  ("а как его сократить?", "подробнее", "а почему?"). A follow-up that makes sense in
  that context is "qa" — do NOT ask to clarify what is already clear from the previous message.

Return ONLY a JSON object — no markdown, no explanation:
{"route": "qa"|"self_check"|"clarify", "topic": "<string or null>", "clarify_message": "<string or null>"}

Examples:
User: "Объясни принцип суперпозиции"
→ {"route": "qa", "topic": null, "clarify_message": null}

User: "Проверь меня по теме дифракция Фраунгофера"
→ {"route": "self_check", "topic": "Дифракция Фраунгофера", "clarify_message": null}

User: "Хочу проверить знания"
→ {"route": "clarify", "topic": null, "clarify_message": "По какой теме хотите провести самопроверку?"}

User: "Test me on Fourier optics"
→ {"route": "self_check", "topic": "Fourier optics", "clarify_message": null}

User: "What is the Huygens–Fresnel principle?"
→ {"route": "qa", "topic": null, "clarify_message": null}"""


_ROUTE_RE = re.compile(r'"route"\s*:\s*"(qa|self_check|clarify)"')
_FIELD_RE = r'"{name}"\s*:\s*"([^"}}]*)'


def _parse_decision(raw: str) -> dict:
    """JSON от LLM; если он битый (GigaChat теряет закрывающую кавычку:
    `"clarify_message": "Что именно?}`) — достаём поля регулярками."""
    start, end = raw.find("{"), raw.rfind("}") + 1
    try:
        return json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        route = _ROUTE_RE.search(raw)
        if not route:
            raise
        data = {"route": route.group(1)}
        for name in ("topic", "clarify_message"):
            m = re.search(_FIELD_RE.format(name=name), raw)
            data[name] = m.group(1).strip() if m else None
        return data


async def plan(
    message: str, request_id: str = "", previous_message: str | None = None
) -> PlannerDecision:
    """previous_message — предыдущий вопрос пользователя в этом чате: без него
    уточнение («а как его сократить?») уходит в clarify вместо ответа."""
    user_content = (
        f"Previous user message: {previous_message}\nCurrent message: {message}"
        if previous_message else message
    )
    try:
        raw = await llm_client.chat(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            # 128 не хватало GigaChat: JSON обрезался → planner_error и лишний
            # вызов LLM впустую (fallback на qa).
            max_tokens=256,
            request_id=request_id,
        )
        data = _parse_decision(raw)

        route = data.get("route", "qa")
        if route not in ("qa", "self_check", "clarify"):
            route = "qa"

        decision = PlannerDecision(
            route=route,
            topic=data.get("topic") or None,
            clarify_message=data.get("clarify_message") or None,
        )
        logger.info("planner_decision", route=route, request_id=request_id)
        return decision

    except Exception as exc:
        logger.error("planner_error", error=str(exc), request_id=request_id)
        # Fallback: treat as Q&A to avoid dead-end for the user
        return PlannerDecision(route="qa", topic=None, clarify_message=None)
