"""
Self-check generator: produces a mixed question set for a given topic.
Questions are grounded in corpus chunks retrieved via RAG.
Returns a QuestionSet with multiple-choice and open-ended questions.
"""
import json
from dataclasses import dataclass, field
from atlas.llm.client import llm_client
from atlas.core.logging import logger


@dataclass
class Question:
    question_id: str
    type: str  # "multiple_choice" | "open_ended"
    prompt: str
    options: list[str] = field(default_factory=list)  # only for multiple_choice
    correct_option: str | None = None  # only for multiple_choice, used internally


@dataclass
class QuestionSet:
    topic: str
    language: str
    questions: list[Question]


_SYSTEM_PROMPT = """You are an academic exam question generator for PhD-level study.
You will be given excerpts from textbooks and study materials, followed by a topic.
Generate a mixed question set that tests understanding of the topic STRICTLY based on the provided excerpts.

Rules:
- Generate exactly 3 multiple_choice and 2 open_ended questions
- Every question must be answerable using information present in the provided excerpts
- Do NOT invent facts, definitions or formulas not mentioned in the excerpts
- Questions must be academically rigorous and test deep understanding
- Multiple choice options must be plausible (no obviously wrong answers)
- Respond in the same language as the topic (Russian or English)

Return a JSON object with this exact structure (ONLY JSON, no markdown, no explanation):
{
  "questions": [
    {
      "question_id": "q1",
      "type": "multiple_choice",
      "prompt": "Question text",
      "options": ["A. option1", "B. option2", "C. option3", "D. option4"],
      "correct_option": "A"
    },
    {
      "question_id": "q2",
      "type": "open_ended",
      "prompt": "Question text",
      "options": [],
      "correct_option": null
    }
  ]
}"""

_SYSTEM_PROMPT_NO_CONTEXT = """You are an academic exam question generator for PhD-level study.
Generate a mixed question set for the given topic.

Rules:
- Generate exactly 3 multiple_choice and 2 open_ended questions
- Questions must be academically rigorous and test deep understanding
- Multiple choice options must be plausible (no obviously wrong answers)
- Respond in the same language as the topic (Russian or English)

Return a JSON object with this exact structure (ONLY JSON, no markdown, no explanation):
{
  "questions": [
    {
      "question_id": "q1",
      "type": "multiple_choice",
      "prompt": "Question text",
      "options": ["A. option1", "B. option2", "C. option3", "D. option4"],
      "correct_option": "A"
    },
    {
      "question_id": "q2",
      "type": "open_ended",
      "prompt": "Question text",
      "options": [],
      "correct_option": null
    }
  ]
}"""

_MAX_CONTEXT_CHARS = 6000  # ~1500 tokens for context, leaves room for output


def _build_messages(topic: str, context_chunks: list[str]) -> list[dict]:
    if not context_chunks:
        return [
            {"role": "system", "content": _SYSTEM_PROMPT_NO_CONTEXT},
            {"role": "user", "content": f"Topic: {topic}"},
        ]

    # Concatenate chunks up to the character limit
    context_parts = []
    total = 0
    for chunk in context_chunks:
        if total + len(chunk) > _MAX_CONTEXT_CHARS:
            break
        context_parts.append(chunk)
        total += len(chunk)

    context_text = "\n\n---\n\n".join(context_parts)
    user_content = f"EXCERPTS FROM STUDY MATERIALS:\n\n{context_text}\n\n---\n\nTOPIC: {topic}"

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


async def generate_question_set(
    topic: str,
    language: str = "ru",
    context_chunks: list[str] | None = None,
    request_id: str = "",
) -> QuestionSet:
    messages = _build_messages(topic, context_chunks or [])
    grounded = bool(context_chunks)

    logger.info(
        "generator_start",
        topic=topic,
        grounded=grounded,
        context_chunks=len(context_chunks) if context_chunks else 0,
        request_id=request_id,
    )

    try:
        raw = await llm_client.chat(
            messages=messages,
            temperature=0.4,
            max_tokens=4096,
            request_id=request_id,
        )
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"LLM returned no JSON object. Raw response: {raw[:200]!r}")
        data = json.loads(raw[start:end])

        questions = [
            Question(
                question_id=q["question_id"],
                type=q["type"],
                prompt=q["prompt"],
                options=q.get("options", []),
                correct_option=q.get("correct_option"),
            )
            for q in data["questions"]
        ]
        logger.info(
            "questions_generated",
            topic=topic,
            count=len(questions),
            grounded=grounded,
            request_id=request_id,
        )
        return QuestionSet(topic=topic, language=language, questions=questions)

    except Exception as exc:
        logger.error("generator_error", error=str(exc), request_id=request_id)
        raise
