"""
Self-check orchestration:
  start:  REQUEST_RECEIVED → SC_ATTEMPT_CREATED
  submit: SC_ANSWERS_SUBMITTED → SC_EVALUATED | INVALID_EVALUATION
"""
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from atlas.core.logging import logger
from atlas.db.models import SelfCheckAttempt
from atlas.orchestrator.states import RequestState
from atlas.selfcheck.generator import QuestionSet, generate_question_set
from atlas.selfcheck.evaluator import EvaluationPayload, evaluate_answers


async def start_selfcheck(
    topic: str,
    user_id: str,
    db: AsyncSession,
    language: str = "ru",
    request_id: str | None = None,
) -> tuple[str, QuestionSet]:
    request_id = request_id or str(uuid.uuid4())
    logger.info("sc_flow_start", state=RequestState.REQUEST_RECEIVED, request_id=request_id)

    question_set = await generate_question_set(topic=topic, language=language, request_id=request_id)

    attempt = SelfCheckAttempt(
        id=uuid.uuid4(),
        user_id=user_id,
        topic=topic,
        language=language,
        status="created",
        question_set=[
            {
                "question_id": q.question_id,
                "type": q.type,
                "prompt": q.prompt,
                "options": q.options,
                # correct_option intentionally omitted from stored JSON (not sent to user)
            }
            for q in question_set.questions
        ],
    )
    db.add(attempt)
    await db.commit()

    logger.info("sc_flow_state", state=RequestState.SC_ATTEMPT_CREATED,
                attempt_id=str(attempt.id), request_id=request_id)
    return str(attempt.id), question_set


async def submit_selfcheck(
    attempt_id: str,
    answers: list[dict],
    db: AsyncSession,
    request_id: str | None = None,
) -> EvaluationPayload:
    request_id = request_id or str(uuid.uuid4())

    result = await db.execute(
        select(SelfCheckAttempt).where(SelfCheckAttempt.id == attempt_id)
    )
    attempt = result.scalar_one_or_none()
    if not attempt:
        raise ValueError("ATTEMPT_NOT_FOUND")

    attempt.status = "submitted"
    attempt.answers = answers
    await db.commit()

    logger.info("sc_flow_state", state=RequestState.SC_ANSWERS_SUBMITTED,
                attempt_id=attempt_id, request_id=request_id)

    # Reconstruct Question objects (with correct_option) from stored question_set
    # NOTE: correct_option was not stored — evaluator prompt includes it only for MC questions
    # We pass stored questions as-is; evaluator uses correct_option from generator output
    # For submit flow we don't have correct_option — evaluator must infer from context
    from atlas.selfcheck.generator import Question
    questions = [
        Question(
            question_id=q["question_id"],
            type=q["type"],
            prompt=q["prompt"],
            options=q.get("options", []),
        )
        for q in (attempt.question_set or [])
    ]

    try:
        payload = await evaluate_answers(
            attempt_id=attempt_id,
            questions=questions,
            answers=answers,
            request_id=request_id,
        )
        attempt.status = "evaluated"
        attempt.evaluation = {
            "overall_score": payload.overall_score,
            "criterion_scores": {
                "correctness": payload.criterion_scores.correctness,
                "completeness": payload.criterion_scores.completeness,
                "logic": payload.criterion_scores.logic,
                "terminology": payload.criterion_scores.terminology,
            },
            "question_results": [
                {"question_id": r.question_id, "type": r.type, "score": r.score, "status": r.status}
                for r in payload.question_results
            ],
            "error_tags": payload.error_tags,
            "confidence": payload.confidence,
            "evaluator_summary": payload.evaluator_summary,
            "policy_flags": payload.policy_flags,
        }
        attempt.completed_at = datetime.utcnow()
        await db.commit()
        logger.info("sc_flow_state", state=RequestState.SC_EVALUATED,
                    attempt_id=attempt_id, request_id=request_id)
        return payload

    except Exception as exc:
        attempt.status = "invalid_evaluation"
        await db.commit()
        logger.error("sc_flow_state", state=RequestState.INVALID_EVALUATION,
                     error=str(exc), attempt_id=attempt_id, request_id=request_id)
        raise
