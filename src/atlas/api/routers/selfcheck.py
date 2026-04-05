import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import get_current_user
from atlas.db.models import User
from atlas.db.session import get_db
from atlas.orchestrator.selfcheck_flow import start_selfcheck, submit_selfcheck

router = APIRouter(prefix="/self-check", tags=["self-check"])


# ── Start ─────────────────────────────────────────────────────────────────────

class SelfCheckStartRequest(BaseModel):
    topic: str
    language: str = "ru"


class QuestionOut(BaseModel):
    question_id: str
    type: str
    prompt: str
    options: list[str] = []


class SelfCheckStartResponse(BaseModel):
    request_id: str
    attempt_id: str
    topic: str
    questions: list[QuestionOut]


@router.post("/start", response_model=SelfCheckStartResponse)
async def selfcheck_start(
    body: SelfCheckStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SelfCheckStartResponse:
    request_id = str(uuid.uuid4())
    attempt_id, question_set = await start_selfcheck(
        topic=body.topic,
        user_id=str(current_user.id),
        db=db,
        language=body.language,
        request_id=request_id,
    )
    return SelfCheckStartResponse(
        request_id=request_id,
        attempt_id=attempt_id,
        topic=body.topic,
        questions=[
            QuestionOut(
                question_id=q.question_id,
                type=q.type,
                prompt=q.prompt,
                options=q.options,
            )
            for q in question_set.questions
        ],
    )


# ── Submit ────────────────────────────────────────────────────────────────────

class AnswerIn(BaseModel):
    question_id: str
    answer_text: str


class CriterionScoresOut(BaseModel):
    correctness: float
    completeness: float
    logic: float
    terminology: float


class SelfCheckSubmitResponse(BaseModel):
    request_id: str
    attempt_id: str
    overall_score: float
    criterion_scores: CriterionScoresOut
    error_tags: list[str]
    evaluator_summary: str
    feedback_summary: str


@router.post("/{attempt_id}/submit", response_model=SelfCheckSubmitResponse)
async def selfcheck_submit(
    attempt_id: str,
    answers: list[AnswerIn],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SelfCheckSubmitResponse:
    request_id = str(uuid.uuid4())
    try:
        payload = await submit_selfcheck(
            attempt_id=attempt_id,
            answers=[{"question_id": a.question_id, "answer_text": a.answer_text} for a in answers],
            db=db,
            request_id=request_id,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "ATTEMPT_NOT_FOUND":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Evaluation failed")

    return SelfCheckSubmitResponse(
        request_id=request_id,
        attempt_id=attempt_id,
        overall_score=payload.overall_score,
        criterion_scores=CriterionScoresOut(
            correctness=payload.criterion_scores.correctness,
            completeness=payload.criterion_scores.completeness,
            logic=payload.criterion_scores.logic,
            terminology=payload.criterion_scores.terminology,
        ),
        error_tags=payload.error_tags,
        evaluator_summary=payload.evaluator_summary,
        feedback_summary=payload.evaluator_summary,
    )
