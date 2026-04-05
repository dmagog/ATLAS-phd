"""
Planner: classifies incoming user message into a route.
Routes: qa | self_check | clarification
"""
import json
from atlas.llm.client import llm_client
from atlas.orchestrator.states import PlannerRoute
from atlas.core.logging import logger

_SYSTEM_PROMPT = """You are a router for an academic study assistant.
Classify the user message into exactly one of these routes:
- "qa": the user is asking a factual or conceptual question that should be answered from study materials
- "self_check": the user wants to test their knowledge on a topic (e.g. "test me on X", "quiz me", "give me questions about")
- "clarification": the message is too vague, off-topic, or cannot be classified

Respond with a single JSON object: {"route": "<route>", "confidence": <0.0-1.0>}
No explanation, no markdown, just JSON."""


async def plan(message: str, request_id: str = "") -> PlannerRoute:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]
    try:
        raw = await llm_client.chat(
            messages=messages,
            temperature=0.0,
            max_tokens=64,
            request_id=request_id,
        )
        # Extract JSON even if there's surrounding whitespace/text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        data = json.loads(raw[start:end])
        route_str = data.get("route", "clarification")
        route = PlannerRoute(route_str) if route_str in PlannerRoute._value2member_map_ else PlannerRoute.CLARIFICATION
        logger.info("planner_decided", route=route.value, confidence=data.get("confidence"), request_id=request_id)
        return route
    except Exception as exc:
        logger.error("planner_error", error=str(exc), request_id=request_id)
        return PlannerRoute.CLARIFICATION
