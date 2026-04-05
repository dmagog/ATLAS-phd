"""
Q&A orchestration flow:
REQUEST_RECEIVED → PLANNER_DECIDED → QA_RETRIEVAL_DONE →
QA_ANSWER_DRAFTED → QA_VERIFIED_PASS/FAIL → RESPONSE_SENT/REFUSAL_SENT
"""
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.logging import logger
from atlas.llm.embeddings import get_embedding
from atlas.orchestrator.states import RefusalReasonCode, RequestState
from atlas.qa.answer import AnswerDraft, Citation, generate_answer
from atlas.qa.verifier import verify
from atlas.retriever.retriever import RetrievalResult, retrieve


_REFUSAL_MESSAGES = {
    RefusalReasonCode.LOW_EVIDENCE: (
        "К сожалению, в учебных материалах недостаточно информации для ответа на этот вопрос. "
        "Попробуйте переформулировать или уточнить тему."
    ),
    RefusalReasonCode.NO_CITATIONS: (
        "Не удалось сформировать ответ с надёжными источниками. "
        "Попробуйте задать вопрос иначе."
    ),
    RefusalReasonCode.POLICY_BLOCKED: "Запрос заблокирован политикой безопасности.",
    RefusalReasonCode.OFF_TOPIC: "Вопрос выходит за пределы учебных материалов.",
}

_FOLLOWUP_SUGGESTIONS = [
    "Попробуйте уточнить конкретный аспект темы.",
    "Используйте режим самопроверки для закрепления материала.",
    "Переформулируйте вопрос с указанием конкретного понятия или термина.",
]


@dataclass
class QAResponse:
    request_id: str
    state: RequestState
    answer_markdown: str | None = None
    citations: list[Citation] = field(default_factory=list)
    followup_suggestions: list[str] = field(default_factory=list)
    refusal_reason_code: str | None = None
    refusal_message: str | None = None


async def run_qa_flow(
    question: str,
    db: AsyncSession,
    response_profile: str = "detailed",
    request_id: str | None = None,
) -> QAResponse:
    request_id = request_id or str(uuid.uuid4())

    logger.info("qa_flow_start", state=RequestState.REQUEST_RECEIVED, request_id=request_id)

    try:
        # Embed query
        query_embedding = await get_embedding(question, request_id=request_id)

        # Retrieve
        retrieval: RetrievalResult = await retrieve(
            query_embedding=query_embedding,
            db=db,
            request_id=request_id,
        )
        logger.info("qa_flow_state", state=RequestState.QA_RETRIEVAL_DONE, request_id=request_id)

        # Early refusal if no evidence at all
        if not retrieval.candidates:
            logger.info("qa_flow_state", state=RequestState.REFUSAL_SENT, request_id=request_id)
            return QAResponse(
                request_id=request_id,
                state=RequestState.REFUSAL_SENT,
                refusal_reason_code=RefusalReasonCode.LOW_EVIDENCE,
                refusal_message=_REFUSAL_MESSAGES[RefusalReasonCode.LOW_EVIDENCE],
                followup_suggestions=_FOLLOWUP_SUGGESTIONS,
            )

        # Generate answer
        draft: AnswerDraft = await generate_answer(
            question=question,
            candidates=retrieval.candidates,
            response_profile=response_profile,
            request_id=request_id,
        )
        logger.info("qa_flow_state", state=RequestState.QA_ANSWER_DRAFTED, request_id=request_id)

        # Verify
        decision = verify(draft=draft, retrieval=retrieval, request_id=request_id)

        if decision.passed:
            logger.info("qa_flow_state", state=RequestState.RESPONSE_SENT, request_id=request_id)
            return QAResponse(
                request_id=request_id,
                state=RequestState.RESPONSE_SENT,
                answer_markdown=draft.answer_markdown,
                citations=draft.citations,
            )
        else:
            logger.info("qa_flow_state", state=RequestState.REFUSAL_SENT,
                        reason=decision.reason_code, request_id=request_id)
            return QAResponse(
                request_id=request_id,
                state=RequestState.REFUSAL_SENT,
                refusal_reason_code=decision.reason_code.value if decision.reason_code else None,
                refusal_message=_REFUSAL_MESSAGES.get(decision.reason_code, "Не удалось сформировать ответ."),
                followup_suggestions=_FOLLOWUP_SUGGESTIONS,
            )

    except Exception as exc:
        logger.error("qa_flow_error", error=str(exc), request_id=request_id)
        return QAResponse(
            request_id=request_id,
            state=RequestState.TECHNICAL_ERROR,
            refusal_message="Произошла техническая ошибка. Попробуйте повторить запрос.",
        )
