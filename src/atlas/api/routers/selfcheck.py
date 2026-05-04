import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import get_current_user
from atlas.db.models import SelfCheckAttempt, User
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SelfCheckStartResponse:
    request_id = str(uuid.uuid4())
    try:
        from atlas.db.tenant_helpers import resolve_tenant_id_for_user
        tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
        attempt_id, question_set = await start_selfcheck(
            topic=body.topic,
            user_id=str(current_user.id),
            tenant_id=tenant_id,
            db=db,
            language=body.language,
            request_id=request_id,
        )
    except Exception as exc:
        msg = str(exc)
        if "rate" in msg.lower() or "429" in msg or "503" in msg:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Превышен лимит запросов к LLM. Подождите минуту и попробуйте снова.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ошибка генерации вопросов от LLM. Попробуйте ещё раз.",
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


class QuestionResultOut(BaseModel):
    question_id: str
    type: str
    prompt: str
    options: list[str] = []
    correct_answer: str | None = None   # letter for MC, None for open-ended
    user_answer: str
    score: float
    status: str  # correct | partial | incorrect


class SelfCheckSubmitResponse(BaseModel):
    request_id: str
    attempt_id: str
    overall_score: float
    criterion_scores: CriterionScoresOut
    error_tags: list[str]
    evaluator_summary: str
    feedback_summary: str
    question_results: list[QuestionResultOut] = []


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

    # Fetch stored attempt to get question details (with correct_option) and user answers
    result_db = await db.execute(
        select(SelfCheckAttempt).where(SelfCheckAttempt.id == attempt_id)
    )
    attempt = result_db.scalar_one_or_none()
    question_map = {q["question_id"]: q for q in (attempt.question_set or [])} if attempt else {}
    answer_map = {a["question_id"]: a["answer_text"] for a in (attempt.answers or [])} if attempt else {}
    score_map = {r.question_id: r for r in payload.question_results}

    question_results_out: list[QuestionResultOut] = []
    for qid, q in question_map.items():
        r = score_map.get(qid)
        question_results_out.append(QuestionResultOut(
            question_id=qid,
            type=q["type"],
            prompt=q["prompt"],
            options=q.get("options", []),
            correct_answer=q.get("correct_option"),
            user_answer=answer_map.get(qid, ""),
            score=r.score if r else 0.0,
            status=r.status if r else "incorrect",
        ))

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
        question_results=question_results_out,
    )


# ── History ───────────────────────────────────────────────────────────────────

class AttemptSummary(BaseModel):
    attempt_id: str
    topic: str
    language: str
    status: str
    overall_score: float | None = None
    created_at: str
    completed_at: str | None = None


class AttemptDetail(BaseModel):
    attempt_id: str
    topic: str
    language: str
    status: str
    overall_score: float | None = None
    criterion_scores: CriterionScoresOut | None = None
    evaluator_summary: str | None = None
    error_tags: list[str] = []
    question_results: list[QuestionResultOut] = []
    created_at: str
    completed_at: str | None = None


def _fmt(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


@router.get("/history/list", response_model=list[AttemptSummary])
async def selfcheck_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AttemptSummary]:
    rows = (await db.execute(
        select(SelfCheckAttempt)
        .where(SelfCheckAttempt.user_id == current_user.id)
        .order_by(desc(SelfCheckAttempt.created_at))
        .limit(limit)
        .offset(offset)
    )).scalars().all()

    result = []
    for a in rows:
        score = None
        if a.evaluation and "overall_score" in a.evaluation:
            score = a.evaluation["overall_score"]
        result.append(AttemptSummary(
            attempt_id=str(a.id),
            topic=a.topic,
            language=a.language,
            status=a.status,
            overall_score=score,
            created_at=_fmt(a.created_at),
            completed_at=_fmt(a.completed_at),
        ))
    return result


@router.get("/{attempt_id}/detail", response_model=AttemptDetail)
async def selfcheck_detail(
    attempt_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AttemptDetail:
    row = (await db.execute(
        select(SelfCheckAttempt).where(
            SelfCheckAttempt.id == attempt_id,
            SelfCheckAttempt.user_id == current_user.id,
        )
    )).scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")

    ev = row.evaluation or {}
    cs_raw = ev.get("criterion_scores", {})
    cs = CriterionScoresOut(
        correctness=cs_raw.get("correctness", 0.0),
        completeness=cs_raw.get("completeness", 0.0),
        logic=cs_raw.get("logic", 0.0),
        terminology=cs_raw.get("terminology", 0.0),
    ) if cs_raw else None

    # Rebuild question results with correct answers and user answers
    question_map = {q["question_id"]: q for q in (row.question_set or [])}
    answer_map   = {a["question_id"]: a["answer_text"] for a in (row.answers or [])}
    score_map    = {r["question_id"]: r for r in ev.get("question_results", [])}

    qr_out = []
    for qid, q in question_map.items():
        r = score_map.get(qid, {})
        qr_out.append(QuestionResultOut(
            question_id=qid,
            type=q["type"],
            prompt=q["prompt"],
            options=q.get("options", []),
            correct_answer=q.get("correct_option"),
            user_answer=answer_map.get(qid, ""),
            score=r.get("score", 0.0),
            status=r.get("status", "incorrect"),
        ))

    return AttemptDetail(
        attempt_id=str(row.id),
        topic=row.topic,
        language=row.language,
        status=row.status,
        overall_score=ev.get("overall_score"),
        criterion_scores=cs,
        evaluator_summary=ev.get("evaluator_summary"),
        error_tags=ev.get("error_tags", []),
        question_results=qr_out,
        created_at=_fmt(row.created_at),
        completed_at=_fmt(row.completed_at),
    )
