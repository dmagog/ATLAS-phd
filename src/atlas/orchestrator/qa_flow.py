"""
Q&A orchestration flow:
REQUEST_RECEIVED → QA_RETRIEVAL_DONE →
  [if not enough_evidence: REFUSAL_SENT (no LLM call)] →
QA_ANSWER_DRAFTED → QA_VERIFIED_PASS/FAIL → [QA_REGEN_ATTEMPT →] RESPONSE_SENT/REFUSAL_SENT

Note: Planner-level routing is handled at the API layer (separate endpoints for Q&A and
self-check). Within the Q&A flow the pipeline is deterministic: embed → retrieve → answer →
verify, with one optional re-generation attempt when the Verifier rejects the first draft.

Hard-gate semantics (M3.A.0 fix):
  Refusal on insufficient evidence happens at the **retrieval** layer, before any LLM call.
  This means:
    * Off-topic / out-of-corpus questions return REFUSAL_SENT in <300ms (no token cost).
    * If the upstream LLM is unavailable (404/timeout/DNS), refusal still works — we never
      depended on the LLM to know we should refuse.
    * The metric `refusal_correctness` (BDD 6.1) is now measurable: legitimate refusals
      surface as `api_status=refused`, not `api_status=error` (TECHNICAL_ERROR).
  When evidence is insufficient on first retrieval, we still try one regen with a wider
  top_k window before refusing — this preserves the original recovery semantic for
  borderline cases.
"""
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.config import settings
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

# When the first retrieval fails enough_evidence or Verifier rejects the draft,
# expand top_k by this multiplier and retry.
_REGEN_TOP_K_MULTIPLIER = 2


def _refusal_response(
    request_id: str,
    reason_code: RefusalReasonCode,
) -> "QAResponse":
    """Build a REFUSAL_SENT response with the appropriate user-facing message."""
    return QAResponse(
        request_id=request_id,
        state=RequestState.REFUSAL_SENT,
        refusal_reason_code=reason_code.value,
        refusal_message=_REFUSAL_MESSAGES.get(reason_code, "Не удалось сформировать ответ."),
        followup_suggestions=_FOLLOWUP_SUGGESTIONS,
    )


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
    conversation_history: list[dict] | None = None,
) -> QAResponse:
    request_id = request_id or str(uuid.uuid4())

    logger.info("qa_flow_start", state=RequestState.REQUEST_RECEIVED, request_id=request_id)

    try:
        # ── Embed ────────────────────────────────────────────────────────────
        query_embedding = await get_embedding(question, request_id=request_id)

        # ── Retrieve (first pass) ─────────────────────────────────────────────
        retrieval: RetrievalResult = await retrieve(
            query_embedding=query_embedding,
            db=db,
            query_text=question,
            request_id=request_id,
        )
        logger.info("qa_flow_state", state=RequestState.QA_RETRIEVAL_DONE, request_id=request_id)

        # Early refusal if corpus returned nothing at all
        if not retrieval.candidates:
            logger.info(
                "qa_flow_state",
                state=RequestState.REFUSAL_SENT,
                reason=RefusalReasonCode.LOW_EVIDENCE,
                gate="retrieval_empty",
                request_id=request_id,
            )
            return _refusal_response(request_id, RefusalReasonCode.LOW_EVIDENCE)

        # ── Hard-gate at retrieval layer (M3.A.0) ─────────────────────────────
        # If the first retrieval has insufficient evidence, try one regen with a wider
        # top_k window. If that ALSO fails enough_evidence — refuse without ever calling
        # the LLM. This keeps refusal correctness independent of LLM availability and
        # avoids burning tokens on off-topic queries.
        if not retrieval.enough_evidence:
            logger.info(
                "qa_flow_regen",
                stage="retrieval",
                first_fail_reason=str(RefusalReasonCode.LOW_EVIDENCE),
                regen_top_k=settings.retriever_top_k * _REGEN_TOP_K_MULTIPLIER,
                request_id=request_id,
            )
            regen_retrieval: RetrievalResult = await retrieve(
                query_embedding=query_embedding,
                db=db,
                top_k=settings.retriever_top_k * _REGEN_TOP_K_MULTIPLIER,
                query_text=question,
                request_id=request_id,
            )
            if not regen_retrieval.enough_evidence or not regen_retrieval.candidates:
                logger.info(
                    "qa_flow_state",
                    state=RequestState.REFUSAL_SENT,
                    reason=RefusalReasonCode.LOW_EVIDENCE,
                    gate="retrieval_hard_gate",
                    request_id=request_id,
                )
                return _refusal_response(request_id, RefusalReasonCode.LOW_EVIDENCE)
            # Wider window did help — proceed to answer with expanded candidates.
            retrieval = regen_retrieval

        # ── Answer ────────────────────────────────────────────────────────────
        # Past this point retrieval.enough_evidence is True. LLM is invoked.
        draft: AnswerDraft = await generate_answer(
            question=question,
            candidates=retrieval.candidates,
            response_profile=response_profile,
            request_id=request_id,
            conversation_history=conversation_history,
        )
        logger.info("qa_flow_state", state=RequestState.QA_ANSWER_DRAFTED, request_id=request_id)

        # ── Verify ────────────────────────────────────────────────────────────
        decision = verify(draft=draft, retrieval=retrieval, request_id=request_id)

        if decision.passed:
            logger.info("qa_flow_state", state=RequestState.RESPONSE_SENT, request_id=request_id)
            return QAResponse(
                request_id=request_id,
                state=RequestState.RESPONSE_SENT,
                answer_markdown=draft.answer_markdown,
                citations=draft.citations,
            )

        # ── Re-generation attempt (NO_CITATIONS path) ─────────────────────────
        # Verifier rejected on citation grounds (e.g., LLM omitted [Doc:] markers).
        # Try one more answer-generation pass on the same retrieval; do not re-run
        # retrieval here because we already verified evidence is sufficient.
        if decision.reason_code == RefusalReasonCode.NO_CITATIONS:
            logger.info(
                "qa_flow_regen",
                stage="answer",
                first_fail_reason=str(decision.reason_code),
                request_id=request_id,
            )
            regen_draft: AnswerDraft = await generate_answer(
                question=question,
                candidates=retrieval.candidates,
                response_profile=response_profile,
                request_id=request_id,
                conversation_history=conversation_history,
            )
            regen_decision = verify(
                draft=regen_draft, retrieval=retrieval, request_id=request_id
            )
            if regen_decision.passed:
                logger.info(
                    "qa_flow_state",
                    state=RequestState.RESPONSE_SENT,
                    via_regen=True,
                    request_id=request_id,
                )
                return QAResponse(
                    request_id=request_id,
                    state=RequestState.RESPONSE_SENT,
                    answer_markdown=regen_draft.answer_markdown,
                    citations=regen_draft.citations,
                )
            decision = regen_decision

        # ── Final refusal ─────────────────────────────────────────────────────
        logger.info(
            "qa_flow_state",
            state=RequestState.REFUSAL_SENT,
            reason=decision.reason_code,
            gate="post_answer",
            request_id=request_id,
        )
        return _refusal_response(
            request_id,
            decision.reason_code or RefusalReasonCode.LOW_EVIDENCE,
        )

    except Exception as exc:
        logger.error("qa_flow_error", error=str(exc), request_id=request_id)
        return QAResponse(
            request_id=request_id,
            state=RequestState.TECHNICAL_ERROR,
            refusal_message="Произошла техническая ошибка. Попробуйте повторить запрос.",
        )
