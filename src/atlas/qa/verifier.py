"""
Verifier: hard-gate that blocks answers with insufficient evidence.
Checks:
  - enough_evidence flag from retriever
  - answer contains at least one citation marker [Doc:
  - no policy violations (placeholder)
"""
from dataclasses import dataclass
from atlas.orchestrator.states import RefusalReasonCode
from atlas.retriever.retriever import RetrievalResult
from atlas.qa.answer import AnswerDraft
from atlas.core.logging import logger


@dataclass
class VerificationDecision:
    passed: bool
    reason_code: RefusalReasonCode | None = None


def verify(
    draft: AnswerDraft,
    retrieval: RetrievalResult,
    request_id: str = "",
) -> VerificationDecision:
    if not retrieval.enough_evidence:
        logger.info("verifier_fail", reason=RefusalReasonCode.LOW_EVIDENCE, request_id=request_id)
        return VerificationDecision(passed=False, reason_code=RefusalReasonCode.LOW_EVIDENCE)

    if "[Doc:" not in draft.answer_markdown:
        logger.info("verifier_fail", reason=RefusalReasonCode.NO_CITATIONS, request_id=request_id)
        return VerificationDecision(passed=False, reason_code=RefusalReasonCode.NO_CITATIONS)

    logger.info("verifier_pass", request_id=request_id)
    return VerificationDecision(passed=True)
