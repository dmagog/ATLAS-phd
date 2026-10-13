"""
Unified chat endpoint.

POST /chat/message
  → Planner decides route
  → qa         : runs qa_flow, returns answer + citations
  → self_check : runs start_selfcheck, returns questions for inline quiz
  → clarify    : returns a follow-up question from the planner

История чатов (таблица `sessions`, переписка — JSON-список в `history`):
  POST   /chat/message            — с session_id продолжает чат, без него создаёт новый
  GET    /chat/sessions           — чаты пользователя в текущей кафедре
  GET    /chat/sessions/{id}      — сообщения чата
  DELETE /chat/sessions/{id}      — удалить свой чат
"""
import uuid
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import get_current_user, require_llm_quota
from atlas.db.models import Session as ChatSession
from atlas.db.models import User
from atlas.db.session import get_db
from atlas.orchestrator.qa_flow import run_qa_flow
from atlas.orchestrator.selfcheck_flow import start_selfcheck
from atlas.qa.planner import plan

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Request ────────────────────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    # Только user/assistant — иначе клиент мог бы инжектировать
    # 'system'-сообщение и переписать instructions поверх legit'ного
    # system prompt в build_answer_prompt.
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message_text: str
    response_profile: str = "detailed"
    language: str = "ru"
    # Устарело: контекст берётся из сохранённого чата (session_id). Поле
    # оставлено для клиентов без истории — используется, только если чата нет.
    conversation_history: list[HistoryMessage] = []
    session_id: str | None = None


# ── Shared sub-models ──────────────────────────────────────────────────────────

class CitationOut(BaseModel):
    document_title: str
    section: str | None = None
    page: int | None = None
    snippet: str


class QuestionOut(BaseModel):
    question_id: str
    type: str
    prompt: str
    options: list[str] = []


# ── Response ───────────────────────────────────────────────────────────────────

class ChatResponse(BaseModel):
    request_id: str
    route: str  # "qa" | "self_check" | "clarify"
    session_id: str | None = None

    # qa fields
    status: str | None = None          # "answered" | "refused" | "error"
    answer_markdown: str | None = None
    citations: list[CitationOut] = []
    refusal_message: str | None = None
    followup_suggestions: list[str] = []

    # self_check fields
    attempt_id: str | None = None
    topic: str | None = None
    questions: list[QuestionOut] = []

    # clarify field
    clarify_message: str | None = None


# ── Handler ────────────────────────────────────────────────────────────────────

# Сколько последних сообщений чата отдаём модели как контекст разговора.
_CONTEXT_MESSAGES = 6
_TITLE_LEN = 80


async def _load_session(db: AsyncSession, session_id: str, user: User, tenant_id) -> ChatSession:
    """Свой чат в текущей кафедре; чужой/несуществующий — 404 (не 403), чтобы
    не подтверждать существование чужого чата."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Чат не найден")
    sess = (await db.execute(
        select(ChatSession).where(
            ChatSession.id == sid,
            ChatSession.user_id == user.id,
            ChatSession.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status_code=404, detail="Чат не найден")
    return sess


def _context_from_history(history: list[dict]) -> list[dict]:
    msgs = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
        and m.get("route", "qa") == "qa" and m.get("status", "answered") == "answered"
    ]
    return msgs[-_CONTEXT_MESSAGES:]


def _assistant_entry(resp: "ChatResponse") -> dict:
    entry = {"role": "assistant", "route": resp.route, "request_id": resp.request_id}
    if resp.route == "qa":
        entry.update(
            status=resp.status,
            content=resp.answer_markdown or resp.refusal_message or "",
            citations=[c.model_dump() for c in resp.citations],
            followup_suggestions=resp.followup_suggestions,
        )
    elif resp.route == "self_check":
        entry.update(
            content=f"Самопроверка: {resp.topic}",
            attempt_id=resp.attempt_id,
            topic=resp.topic,
            questions=[q.model_dump() for q in resp.questions],
        )
    else:
        entry.update(content=resp.clarify_message or "")
    return entry


@router.post("/message", response_model=ChatResponse)
async def chat_message(
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _quota: User = Depends(require_llm_quota),
) -> ChatResponse:
    from atlas.db.tenant_helpers import assert_tenant_writable, resolve_tenant_id_for_user
    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    await assert_tenant_writable(tenant_id, db, current_user)

    sess = (await _load_session(db, body.session_id, current_user, tenant_id)
            if body.session_id else None)
    if sess is not None:
        body.conversation_history = [
            HistoryMessage(**m) for m in _context_from_history(sess.history or [])
        ]

    resp = await _handle_message(body, request, db, current_user)

    now = datetime.utcnow()
    if sess is None:
        sess = ChatSession(
            id=uuid.uuid4(), tenant_id=tenant_id, user_id=current_user.id,
            mode="qa", response_profile=body.response_profile, history=[], created_at=now,
        )
        db.add(sess)
    # JSON-колонка: присваиваем новый список, иначе SQLAlchemy не увидит изменение.
    sess.history = (sess.history or []) + [
        {"role": "user", "content": body.message_text, "ts": now.isoformat()},
        {**_assistant_entry(resp), "ts": datetime.utcnow().isoformat()},
    ]
    sess.response_profile = body.response_profile
    sess.updated_at = datetime.utcnow()
    await db.commit()
    resp.session_id = str(sess.id)
    return resp


class ChatSessionSummary(BaseModel):
    session_id: str
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ChatSessionDetail(ChatSessionSummary):
    response_profile: str
    messages: list[dict]


def _title(history: list[dict]) -> str:
    first = next((m["content"] for m in history if m.get("role") == "user"), "") or "Без названия"
    return first if len(first) <= _TITLE_LEN else first[:_TITLE_LEN - 1].rstrip() + "…"


@router.get("/sessions", response_model=list[ChatSessionSummary])
async def list_sessions(
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatSessionSummary]:
    from atlas.db.tenant_helpers import resolve_tenant_id_for_user
    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    rows = (await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id, ChatSession.tenant_id == tenant_id)
        .order_by(desc(ChatSession.updated_at))
        .limit(limit)
    )).scalars().all()
    return [
        ChatSessionSummary(
            session_id=str(r.id), title=_title(r.history or []),
            message_count=len(r.history or []), created_at=r.created_at, updated_at=r.updated_at,
        )
        for r in rows if r.history
    ]


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_session(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionDetail:
    from atlas.db.tenant_helpers import resolve_tenant_id_for_user
    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    sess = await _load_session(db, session_id, current_user, tenant_id)
    history = sess.history or []
    return ChatSessionDetail(
        session_id=str(sess.id), title=_title(history), message_count=len(history),
        created_at=sess.created_at, updated_at=sess.updated_at,
        response_profile=sess.response_profile, messages=history,
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    from atlas.db.tenant_helpers import resolve_tenant_id_for_user
    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    sess = await _load_session(db, session_id, current_user, tenant_id)
    await db.delete(sess)
    await db.commit()
    return Response(status_code=204)


async def _handle_message(
    body: ChatRequest,
    request: Request,
    db: AsyncSession,
    current_user: User,
) -> ChatResponse:
    request_id = str(uuid.uuid4())

    # M4.A: write-блок на read-only / archived тенанте — в chat_message до
    # вызова (теперь каждый route пишет историю чата, clarify тоже).

    # ── Planner ───────────────────────────────────────────────────────────────
    previous = next(
        (m.content for m in reversed(body.conversation_history) if m.role == "user"), None
    )
    decision = await plan(
        message=body.message_text, request_id=request_id, previous_message=previous
    )

    # ── Route: clarify ────────────────────────────────────────────────────────
    if decision.route == "clarify":
        return ChatResponse(
            request_id=request_id,
            route="clarify",
            clarify_message=decision.clarify_message or "Уточните, пожалуйста, ваш запрос.",
        )

    # ── Route: self_check ─────────────────────────────────────────────────────
    if decision.route == "self_check":
        topic = decision.topic or body.message_text
        try:
            from atlas.db.tenant_helpers import resolve_tenant_id_for_user
            tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
            attempt_id, question_set = await start_selfcheck(
                topic=topic,
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
                detail="Ошибка генерации вопросов. Попробуйте ещё раз.",
            )
        return ChatResponse(
            request_id=request_id,
            route="self_check",
            attempt_id=attempt_id,
            topic=topic,
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

    # ── Route: qa (default) ───────────────────────────────────────────────────
    history = [{"role": m.role, "content": m.content} for m in body.conversation_history]
    # tenant_id may already be resolved above (in the self_check branch) — do
    # it here too for safety; resolve_tenant_id_for_user is cheap (cached).
    from atlas.db.tenant_helpers import resolve_tenant_id_for_user
    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    result = await run_qa_flow(
        question=body.message_text,
        db=db,
        tenant_id=tenant_id,
        response_profile=body.response_profile,
        request_id=request_id,
        conversation_history=history or None,
    )

    if result.answer_markdown:
        qa_status = "answered"
    elif result.state.value == "TECHNICAL_ERROR":
        qa_status = "error"
    else:
        qa_status = "refused"

    return ChatResponse(
        request_id=request_id,
        route="qa",
        status=qa_status,
        answer_markdown=result.answer_markdown,
        citations=[
            CitationOut(
                document_title=c.document_title,
                section=c.section,
                page=c.page,
                snippet=c.snippet,
            )
            for c in result.citations
        ],
        followup_suggestions=result.followup_suggestions,
        refusal_message=result.refusal_message,
    )
