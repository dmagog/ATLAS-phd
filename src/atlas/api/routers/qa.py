import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import get_current_user
from atlas.core.logging import logger
from atlas.db.models import QAFeedback, User
from atlas.db.session import get_db
from atlas.orchestrator.qa_flow import run_qa_flow

router = APIRouter(prefix="/qa", tags=["qa"])


class HistoryMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class QARequest(BaseModel):
    session_id: str | None = None
    message_text: str
    response_profile: str = "detailed"
    conversation_history: list[HistoryMessage] = []


class CitationOut(BaseModel):
    document_title: str
    section: str | None = None
    page: int | None = None
    snippet: str


class QAResponse(BaseModel):
    request_id: str
    status: str  # "answered" | "refused" | "error"
    answer_markdown: str | None = None
    citations: list[CitationOut] = []
    followup_suggestions: list[str] = []
    refusal_reason_code: str | None = None
    refusal_message: str | None = None


@router.post("/message", response_model=QAResponse)
async def qa_message(
    body: QARequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QAResponse:
    request_id = str(uuid.uuid4())
    history = [{"role": m.role, "content": m.content} for m in body.conversation_history]
    result = await run_qa_flow(
        question=body.message_text,
        db=db,
        response_profile=body.response_profile,
        request_id=request_id,
        conversation_history=history or None,
    )

    if result.answer_markdown:
        status = "answered"
    elif result.state.value == "TECHNICAL_ERROR":
        status = "error"
    else:
        status = "refused"

    return QAResponse(
        request_id=result.request_id,
        status=status,
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
        refusal_reason_code=result.refusal_reason_code,
        refusal_message=result.refusal_message,
    )


class FeedbackRequest(BaseModel):
    request_id: str
    rating: str          # "positive" | "negative"
    question_text: str | None = None
    answer_markdown: str | None = None


@router.post("/feedback", status_code=204)
async def qa_feedback(
    body: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    if body.rating not in ("positive", "negative"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rating must be 'positive' or 'negative'",
        )
    feedback = QAFeedback(
        id=uuid.uuid4(),
        user_id=current_user.id,
        request_id=body.request_id,
        rating=body.rating,
        question_text=body.question_text,
        answer_markdown=body.answer_markdown,
    )
    db.add(feedback)
    await db.commit()
    logger.info(
        "qa_feedback_saved",
        request_id=body.request_id,
        rating=body.rating,
        user_id=str(current_user.id),
    )
