import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import get_current_user, require_llm_quota
from atlas.db.models import Program, ProgramTopic, SelfCheckAttempt, Tenant, User
from atlas.db.session import get_db
from atlas.orchestrator.selfcheck_flow import start_selfcheck, submit_selfcheck

router = APIRouter(prefix="/self-check", tags=["self-check"])


# ── Start ─────────────────────────────────────────────────────────────────────

class SelfCheckStartRequest(BaseModel):
    topic: str
    language: str = "ru"
    # Номер темы активной программы (external_id, например «4.5.11»), если
    # попытка начата по билету. Без него тема ищется по тексту (title или
    # «title (section)»); «своя тема» остаётся без topic_id.
    topic_external_id: str | None = None


async def _resolve_topic_id(
    db: AsyncSession, tenant_id, external_id: str | None, topic_text: str
):
    program_id = (await db.execute(
        select(Program.id).where(Program.tenant_id == tenant_id, Program.status == "active")
    )).scalar_one_or_none()
    if program_id is None:
        return None
    topics = (await db.execute(
        select(ProgramTopic).where(ProgramTopic.program_id == program_id)
    )).scalars().all()
    if external_id:
        return next((t.id for t in topics if t.external_id == external_id), None)
    text = topic_text.strip().lower()
    return next(
        (t.id for t in topics
         if text == t.title.lower() or text == f"{t.title} ({t.section})".lower()),
        None,
    )


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
    _quota: User = Depends(require_llm_quota),
) -> SelfCheckStartResponse:
    request_id = str(uuid.uuid4())
    try:
        from atlas.db.tenant_helpers import assert_tenant_writable, resolve_tenant_id_for_user
        tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
        await assert_tenant_writable(tenant_id, db, current_user)
        topic_id = await _resolve_topic_id(db, tenant_id, body.topic_external_id, body.topic)
        attempt_id, question_set = await start_selfcheck(
            topic=body.topic,
            user_id=str(current_user.id),
            tenant_id=tenant_id,
            db=db,
            language=body.language,
            request_id=request_id,
            topic_id=topic_id,
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
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _quota: User = Depends(require_llm_quota),
) -> SelfCheckSubmitResponse:
    request_id = str(uuid.uuid4())
    from atlas.db.tenant_helpers import assert_tenant_writable, resolve_tenant_id_for_user
    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    await assert_tenant_writable(tenant_id, db, current_user)
    # Защита от IDOR: super-admin может работать в любом tenant'е через
    # X-Atlas-Tenant header, но обычные пользователи (student/supervisor/
    # tenant-admin) обязаны быть владельцем попытки. tenant_id/user_id
    # пробрасываются в orchestrator и в финальный fetch ниже.
    from atlas.db.models import UserRole
    is_super = current_user.role == UserRole.super_admin.value
    scope_user_id = None if is_super else current_user.id
    try:
        payload = await submit_selfcheck(
            attempt_id=attempt_id,
            answers=[{"question_id": a.question_id, "answer_text": a.answer_text} for a in answers],
            db=db,
            request_id=request_id,
            tenant_id=tenant_id,
            user_id=scope_user_id,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "ATTEMPT_NOT_FOUND":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Evaluation failed")

    # Fetch stored attempt to get question details (with correct_option) and user answers.
    # Те же фильтры по tenant/user, что и при submit'е — иначе 404 на стадии fetch.
    fetch_stmt = select(SelfCheckAttempt).where(
        SelfCheckAttempt.id == attempt_id,
        SelfCheckAttempt.tenant_id == tenant_id,
    )
    if scope_user_id is not None:
        fetch_stmt = fetch_stmt.where(SelfCheckAttempt.user_id == scope_user_id)
    result_db = await db.execute(fetch_stmt)
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
    tenant_slug: str | None = None
    tenant_name: str | None = None
    # Тема программы, если попытка привязана к билету (иначе «своя тема»).
    topic_external_id: str | None = None
    topic_title: str | None = None


class HistoryFacetTenant(BaseModel):
    slug: str
    name: str
    count: int


class HistoryFacetTopic(BaseModel):
    key: str  # «<tenant_slug>:<external_id>» или CUSTOM_TOPIC_KEY
    tenant_slug: str
    external_id: str | None
    title: str
    section: str | None
    count: int


class HistoryFacets(BaseModel):
    tenants: list[HistoryFacetTenant]
    topics: list[HistoryFacetTopic]


# Значение фильтра «тема» для попыток без привязки к билету.
CUSTOM_TOPIC_KEY = "custom"


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


def _history_query(user_id):
    """Попытки пользователя по всем его кафедрам (для привязанных ролей — одна)
    + кафедра и тема программы. Тема — по (кафедра, external_id): при новой
    версии программы id тем меняются, номер билета — нет."""
    return (
        select(SelfCheckAttempt, Tenant, ProgramTopic)
        .join(Tenant, Tenant.id == SelfCheckAttempt.tenant_id)
        .outerjoin(ProgramTopic, ProgramTopic.id == SelfCheckAttempt.topic_id)
        .where(SelfCheckAttempt.user_id == user_id)
    )


@router.get("/history/list", response_model=list[AttemptSummary])
async def selfcheck_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: str | None = Query(default=None, description="slug кафедры"),
    topic: str | None = Query(default=None, description="ключ темы из /history/facets"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AttemptSummary]:
    stmt = _history_query(current_user.id)
    if tenant:
        stmt = stmt.where(Tenant.slug == tenant)
    if topic == CUSTOM_TOPIC_KEY:
        stmt = stmt.where(SelfCheckAttempt.topic_id.is_(None))
    elif topic and ":" in topic:
        topic_tenant, external_id = topic.split(":", 1)
        stmt = stmt.where(Tenant.slug == topic_tenant, ProgramTopic.external_id == external_id)
    rows = (await db.execute(
        stmt.order_by(desc(SelfCheckAttempt.created_at)).limit(limit).offset(offset)
    )).all()

    result = []
    for a, t, pt in rows:
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
            tenant_slug=t.slug,
            tenant_name=t.display_name,
            topic_external_id=pt.external_id if pt else None,
            topic_title=pt.title if pt else None,
        ))
    return result


@router.get("/history/facets", response_model=HistoryFacets)
async def selfcheck_history_facets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HistoryFacets:
    """Варианты для фильтров истории: только то, что есть в попытках пользователя."""
    rows = (await db.execute(_history_query(current_user.id))).all()
    tenants: dict[str, HistoryFacetTenant] = {}
    topics: dict[str, HistoryFacetTopic] = {}
    for _a, t, pt in rows:
        tf = tenants.setdefault(t.slug, HistoryFacetTenant(slug=t.slug, name=t.display_name, count=0))
        tf.count += 1
        if pt is not None:
            key = f"{t.slug}:{pt.external_id}"
            fallback = HistoryFacetTopic(key=key, tenant_slug=t.slug, external_id=pt.external_id,
                                         title=pt.title, section=pt.section, count=0)
        else:
            key = f"{t.slug}:{CUSTOM_TOPIC_KEY}"
            fallback = HistoryFacetTopic(key=CUSTOM_TOPIC_KEY, tenant_slug=t.slug, external_id=None,
                                         title="Свои темы", section=None, count=0)
        topics.setdefault(key, fallback).count += 1

    def _order(f: HistoryFacetTopic):
        # Билеты по номеру (4.5.10 после 4.5.9), «Свои темы» — в конце.
        nums = [int(x) for x in (f.external_id or "").split(".") if x.isdigit()]
        return (f.tenant_slug, f.external_id is None, nums)

    return HistoryFacets(
        tenants=sorted(tenants.values(), key=lambda f: f.name),
        topics=sorted(topics.values(), key=_order),
    )


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


# ── Evaluate (debug) ─────────────────────────────────────────────────────────


class EvaluateDebugRequest(BaseModel):
    """Debug endpoint для eval-runner'а: оценить пару (question, user_answer) без
    создания attempt'а. Используется при self_check блоке eval-set'а, где у нас
    уже есть canned_question — runner не должен полагаться на /start, который
    генерит свои вопросы.
    """
    question: str
    question_type: str = "open_ended"  # "open_ended" | "multiple_choice"
    options: list[str] = []
    correct_option: str | None = None
    user_answer: str


class EvaluateDebugResponse(BaseModel):
    overall_score: float
    criterion_scores: CriterionScoresOut
    error_tags: list[str]
    evaluator_summary: str
    confidence: float


@router.post("/evaluate", response_model=EvaluateDebugResponse)
async def selfcheck_evaluate_debug(
    body: EvaluateDebugRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EvaluateDebugResponse:
    """Eval-only stateless evaluator для measurement self-check rubric correctness.

    Не создаёт attempt в БД, не пишет audit. Используется только runner'ом
    eval'а — поэтому ограничен administrator-ролью.
    """
    if current_user.role not in ("super-admin", "tenant-admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin only")

    from atlas.selfcheck.evaluator import evaluate_answers
    from atlas.selfcheck.generator import Question

    qid = "debug-q1"
    question = Question(
        question_id=qid,
        type=body.question_type,
        prompt=body.question,
        options=body.options,
        correct_option=body.correct_option,
    )
    request_id = str(uuid.uuid4())
    try:
        payload = await evaluate_answers(
            attempt_id=f"debug-{request_id}",
            questions=[question],
            answers=[{"question_id": qid, "answer_text": body.user_answer}],
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    cs = payload.criterion_scores
    return EvaluateDebugResponse(
        overall_score=payload.overall_score,
        criterion_scores=CriterionScoresOut(
            correctness=cs.correctness,
            completeness=cs.completeness,
            logic=cs.logic,
            terminology=cs.terminology,
        ),
        error_tags=payload.error_tags,
        evaluator_summary=payload.evaluator_summary,
        confidence=payload.confidence,
    )
