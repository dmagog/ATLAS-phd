"""
Planner node: classifies user intent and routes to the appropriate flow.

Routes:
  qa         — user wants an answer to a question about study materials
  self_check — user wants to test their knowledge on a topic
  clarify    — intent is ambiguous, ask a follow-up question
"""
import json
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


async def plan(message: str, request_id: str = "") -> PlannerDecision:
    try:
        raw = await llm_client.chat(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0.0,
            max_tokens=128,
            request_id=request_id,
        )
        start = raw.find("{")
        end = raw.rfind("}") + 1
        data = json.loads(raw[start:end])

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
