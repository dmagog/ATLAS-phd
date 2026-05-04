"""
Unified chat endpoint.

POST /chat/message
  → Planner decides route
  → qa         : runs qa_flow, returns answer + citations
  → self_check : runs start_selfcheck, returns questions for inline quiz
  → clarify    : returns a follow-up question from the planner
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import get_current_user
from atlas.db.models import User
from atlas.db.session import get_db
from atlas.orchestrator.qa_flow import run_qa_flow
from atlas.orchestrator.selfcheck_flow import start_selfcheck
from atlas.qa.planner import plan

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Request ────────────────────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message_text: str
    response_profile: str = "detailed"
    language: str = "ru"
    conversation_history: list[HistoryMessage] = []


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

@router.post("/message", response_model=ChatResponse)
async def chat_message(
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    request_id = str(uuid.uuid4())

    # ── Planner ───────────────────────────────────────────────────────────────
    decision = await plan(message=body.message_text, request_id=request_id)

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
