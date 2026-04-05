"""
Self-check generator: produces a mixed question set for a given topic.
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
Generate a mixed question set for the given topic.
Return a JSON object with this exact structure:
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
}

Rules:
- Generate exactly 3 multiple_choice and 2 open_ended questions
- Questions must be academically rigorous and test deep understanding
- Multiple choice options must be plausible (no obviously wrong answers)
- Respond in the same language as the topic (Russian or English)
- Return ONLY the JSON object, no markdown, no explanation"""


async def generate_question_set(
    topic: str,
    language: str = "ru",
    request_id: str = "",
) -> QuestionSet:
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"Topic: {topic}"},
    ]

    try:
        raw = await llm_client.chat(
            messages=messages,
            temperature=0.4,
            max_tokens=1500,
            request_id=request_id,
        )
        start = raw.find("{")
        end = raw.rfind("}") + 1
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
        logger.info("questions_generated", topic=topic, count=len(questions), request_id=request_id)
        return QuestionSet(topic=topic, language=language, questions=questions)

    except Exception as exc:
        logger.error("generator_error", error=str(exc), request_id=request_id)
        raise
