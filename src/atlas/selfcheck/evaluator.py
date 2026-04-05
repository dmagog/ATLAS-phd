"""
Self-check evaluator: scores user answers against a rubric.

Rubric (0-5 scale per criterion):
  - correctness:   40%
  - completeness:  30%
  - logic:         20%
  - terminology:   10%

Overall score = weighted average of criterion scores.
"""
import json
from dataclasses import dataclass, field
from atlas.llm.client import llm_client
from atlas.selfcheck.generator import Question
from atlas.core.logging import logger


@dataclass
class CriterionScores:
    correctness: float
    completeness: float
    logic: float
    terminology: float


@dataclass
class QuestionResult:
    question_id: str
    type: str
    score: float
    status: str  # "correct" | "partial" | "incorrect"


@dataclass
class EvaluationPayload:
    attempt_id: str
    overall_score: float
    criterion_scores: CriterionScores
    question_results: list[QuestionResult]
    error_tags: list[str]
    confidence: float
    evaluator_summary: str
    policy_flags: dict


_SYSTEM_PROMPT = """You are an academic exam evaluator for PhD-level study.
Evaluate the student's answers against the questions provided.

Scoring rubric (0-5 scale for each criterion):
- correctness (40%): factual accuracy of the answer
- completeness (30%): how fully the question is answered
- logic (20%): quality of reasoning and argumentation
- terminology (10%): correct use of domain-specific terms

For multiple-choice questions: score 5 if correct, 0 if wrong.
For open-ended questions: score each criterion 0-5.

Return a JSON object with this exact structure:
{
  "overall_score": <weighted average 0-5>,
  "criterion_scores": {
    "correctness": <0-5>,
    "completeness": <0-5>,
    "logic": <0-5>,
    "terminology": <0-5>
  },
  "question_results": [
    {"question_id": "q1", "type": "multiple_choice", "score": <0-5>, "status": "correct|partial|incorrect"},
    ...
  ],
  "error_tags": ["terminology", "incomplete", "logic_gap"],
  "confidence": <0.0-1.0>,
  "evaluator_summary": "2-4 sentences of constructive feedback in the student's language",
  "policy_flags": {
    "low_confidence": <bool>,
    "inconsistent_eval": <bool>,
    "needs_review": <bool>
  }
}

Return ONLY the JSON object, no markdown, no explanation."""


def _build_eval_prompt(
    questions: list[Question],
    answers: list[dict],
) -> list[dict]:
    qa_pairs = []
    answer_map = {a["question_id"]: a["answer_text"] for a in answers}

    for q in questions:
        answer = answer_map.get(q.question_id, "[no answer provided]")
        line = f"Q ({q.type}) [{q.question_id}]: {q.prompt}"
        if q.options:
            line += "\nOptions: " + " | ".join(q.options)
        if q.correct_option:
            line += f"\nCorrect answer: {q.correct_option}"
        line += f"\nStudent answer: {answer}"
        qa_pairs.append(line)

    content = "\n\n".join(qa_pairs)
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def _validate_payload(data: dict) -> bool:
    required = {"overall_score", "criterion_scores", "question_results",
                 "error_tags", "confidence", "evaluator_summary", "policy_flags"}
    if not required.issubset(data.keys()):
        return False
    cs = data.get("criterion_scores", {})
    if not {"correctness", "completeness", "logic", "terminology"}.issubset(cs.keys()):
        return False
    score = data.get("overall_score", -1)
    if not (0 <= score <= 5):
        return False
    return True


async def evaluate_answers(
    attempt_id: str,
    questions: list[Question],
    answers: list[dict],
    request_id: str = "",
) -> EvaluationPayload:
    messages = _build_eval_prompt(questions, answers)

    raw = await llm_client.chat(
        messages=messages,
        temperature=0.1,
        max_tokens=1500,
        request_id=request_id,
    )

    start = raw.find("{")
    end = raw.rfind("}") + 1
    data = json.loads(raw[start:end])

    if not _validate_payload(data):
        logger.error("evaluator_invalid_payload", attempt_id=attempt_id, request_id=request_id)
        raise ValueError("INVALID_EVALUATION_PAYLOAD")

    cs = data["criterion_scores"]
    payload = EvaluationPayload(
        attempt_id=attempt_id,
        overall_score=float(data["overall_score"]),
        criterion_scores=CriterionScores(
            correctness=float(cs["correctness"]),
            completeness=float(cs["completeness"]),
            logic=float(cs["logic"]),
            terminology=float(cs["terminology"]),
        ),
        question_results=[
            QuestionResult(
                question_id=r["question_id"],
                type=r["type"],
                score=float(r["score"]),
                status=r["status"],
            )
            for r in data["question_results"]
        ],
        error_tags=data.get("error_tags", []),
        confidence=float(data.get("confidence", 1.0)),
        evaluator_summary=data.get("evaluator_summary", ""),
        policy_flags=data.get("policy_flags", {}),
    )

    logger.info(
        "evaluation_done",
        attempt_id=attempt_id,
        overall_score=payload.overall_score,
        confidence=payload.confidence,
        request_id=request_id,
    )
    return payload
