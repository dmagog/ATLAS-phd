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
    # Тема программы, к которой относится вопрос (набор по нескольким темам —
    # «Вся программа»); для набора по одной теме None.
    topic: str | None = None


@dataclass
class QuestionSet:
    topic: str
    language: str
    questions: list[Question]


_SYSTEM_PROMPT = """You are an academic exam question generator for PhD-level study.
You will be given excerpts from textbooks and study materials, followed by a topic.
Generate a mixed question set that tests understanding of the topic STRICTLY based on the provided excerpts.

Rules:
- Generate exactly {N_MC} multiple_choice and {N_OPEN} open_ended questions
- Every question must be answerable using information present in the provided excerpts
- Do NOT invent facts, definitions or formulas not mentioned in the excerpts
- Questions must be academically rigorous and test deep understanding
- Multiple choice options must be plausible (no obviously wrong answers)
- Respond in the same language as the topic (Russian or English)
- Write ALL mathematical formulas and expressions in LaTeX notation enclosed in $...$ for inline or $$...$$ for display math (e.g. $k^2 = -\gamma^2$, $$\sin\theta = \frac{\lambda}{d}$$)
- Never write formulas as plain text substitutes (no "k^2", no "sin(theta)", no unicode subscripts)

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
- Generate exactly {N_MC} multiple_choice and {N_OPEN} open_ended questions
- Questions must be academically rigorous and test deep understanding
- Multiple choice options must be plausible (no obviously wrong answers)
- Respond in the same language as the topic (Russian or English)
- Write ALL mathematical formulas and expressions in LaTeX notation enclosed in $...$ for inline or $$...$$ for display math (e.g. $k^2 = -\gamma^2$, $$\sin\theta = \frac{\lambda}{d}$$)
- Never write formulas as plain text substitutes (no "k^2", no "sin(theta)", no unicode subscripts)

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

_SYSTEM_PROMPT_MULTI = """You are an academic exam question generator for PhD-level study.
You will be given several numbered topics of a study program, each with excerpts from study materials
and the number of questions required for it.
Generate a mixed question set STRICTLY based on the provided excerpts.

Rules:
- For every topic generate exactly the number of questions stated for it — no more, no less
- In total: exactly {N_MC} multiple_choice and {N_OPEN} open_ended questions
- Each question must be answerable using the excerpts of ITS topic; do NOT invent facts
- Multiple choice options must be plausible (no obviously wrong answers)
- Respond in the same language as the topics (Russian or English)
- Write ALL mathematical formulas in LaTeX notation enclosed in $...$ or $$...$$
- Set "topic" of every question to the exact topic label given after «TOPIC N:»

Return a JSON object with this exact structure (ONLY JSON, no markdown, no explanation):
{
  "questions": [
    {
      "question_id": "q1",
      "topic": "<topic label>",
      "type": "multiple_choice",
      "prompt": "Question text",
      "options": ["A. option1", "B. option2", "C. option3", "D. option4"],
      "correct_option": "A"
    },
    {
      "question_id": "q2",
      "topic": "<topic label>",
      "type": "open_ended",
      "prompt": "Question text",
      "options": [],
      "correct_option": null
    }
  ]
}"""

_MAX_CONTEXT_CHARS = 6000  # ~1500 tokens for context, leaves room for output
# Набор по нескольким темам: ~1500 символов на тему, до 10 тем в одном вызове.
_MAX_CONTEXT_CHARS_PER_TOPIC = 1500


def _with_counts(prompt: str, n_mc: int, n_open: int) -> str:
    return prompt.replace("{N_MC}", str(n_mc)).replace("{N_OPEN}", str(n_open))


def _build_messages(
    topic: str, context_chunks: list[str], n_mc: int = 3, n_open: int = 2
) -> list[dict]:
    if not context_chunks:
        return [
            {"role": "system", "content": _with_counts(_SYSTEM_PROMPT_NO_CONTEXT, n_mc, n_open)},
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
        {"role": "system", "content": _with_counts(_SYSTEM_PROMPT, n_mc, n_open)},
        {"role": "user", "content": user_content},
    ]


def _build_multi_messages(
    topics: list[tuple[str, int, list[str]]], n_mc: int, n_open: int
) -> list[dict]:
    """topics: (метка темы, сколько вопросов, фрагменты материалов)."""
    parts = []
    for i, (label, count, chunks) in enumerate(topics, start=1):
        excerpt, total = [], 0
        for chunk in chunks:
            if total + len(chunk) > _MAX_CONTEXT_CHARS_PER_TOPIC and excerpt:
                break
            excerpt.append(chunk[:_MAX_CONTEXT_CHARS_PER_TOPIC])
            total += len(chunk)
        parts.append(
            f"TOPIC {i}: {label}\nQUESTIONS FOR THIS TOPIC: {count}\nEXCERPTS:\n"
            + "\n\n".join(excerpt)
        )
    return [
        {"role": "system", "content": _with_counts(_SYSTEM_PROMPT_MULTI, n_mc, n_open)},
        {"role": "user", "content": "\n\n=====\n\n".join(parts)},
    ]


# GigaChat в русских наборах иногда пишет варианты кириллицей («А. …», ключ
# «Б»). Приводим к латинице A–D: интерфейс берёт ответ по первой букве
# варианта, а оценка MC сравнивает её с ключом строго.
_CYR_TO_LAT = str.maketrans({"А": "A", "Б": "B", "В": "C", "Г": "D", "Д": "E"})


def normalize_option_letter(letter: str | None) -> str | None:
    if not letter:
        return letter
    return letter.strip().upper().translate(_CYR_TO_LAT)[:1] or None


def _normalize_options(options: list[str]) -> list[str]:
    return [o[:1].translate(_CYR_TO_LAT) + o[1:] if o else o for o in options]


def _question_type(q: dict) -> str:
    # Тип — по структуре, а не по строке от LLM (бывает «open_ened»):
    # есть варианты и правильный ответ → MC, иначе открытый вопрос.
    return "multiple_choice" if q.get("options") and q.get("correct_option") else "open_ended"


def _match_topic(raw_topic: str | None, labels: list[str]) -> str | None:
    """Метку темы от LLM приводим к одной из переданных: модель иногда пишет
    «5: …» или обрезает название. Сначала точное совпадение, затем по номеру
    билета (начало метки), по названию темы, по номеру «TOPIC N»."""
    if not labels:
        return raw_topic
    if raw_topic in labels:
        return raw_topic
    text = (raw_topic or "").strip()
    for label in labels:
        ext = label.split(" ", 1)[0]
        if text.startswith(ext + " ") or text == ext:
            return label
    for label in labels:
        title = label.split(" ", 1)[-1]
        if title and title.lower() in text.lower():
            return label
    head = text.split(":", 1)[0].replace("TOPIC", "").strip()
    if head.isdigit() and 1 <= int(head) <= len(labels):
        return labels[int(head) - 1]
    return None


def _parse_questions(raw: str, topic_labels: list[str] | None = None) -> list[Question]:
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"LLM returned no JSON object. Raw response: {raw[:200]!r}")
    data = json.loads(raw[start:end])
    return [
        Question(
            question_id=q["question_id"],
            type=_question_type(q),
            prompt=q["prompt"],
            options=_normalize_options(q.get("options", [])) if _question_type(q) == "multiple_choice" else [],
            correct_option=normalize_option_letter(q.get("correct_option")) if _question_type(q) == "multiple_choice" else None,
            topic=_match_topic(q.get("topic"), topic_labels or []) if topic_labels else q.get("topic"),
        )
        for q in data["questions"]
    ]


async def generate_multi_topic_questions(
    topics: list[tuple[str, int, list[str]]],
    n_mc: int,
    n_open: int,
    request_id: str = "",
) -> list[Question]:
    """Один вызов LLM на порцию тем (оркестратор режет набор на порции ≤10)."""
    raw = await llm_client.chat(
        messages=_build_multi_messages(topics, n_mc, n_open),
        temperature=0.4,
        max_tokens=4096,
        request_id=request_id,
    )
    questions = _parse_questions(raw, [label for label, _count, _chunks in topics])
    logger.info("questions_generated_multi", topics=len(topics), count=len(questions),
                request_id=request_id)
    return questions


async def generate_question_set(
    topic: str,
    language: str = "ru",
    context_chunks: list[str] | None = None,
    request_id: str = "",
    n_mc: int = 3,
    n_open: int = 2,
) -> QuestionSet:
    messages = _build_messages(topic, context_chunks or [], n_mc, n_open)
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
        questions = _parse_questions(raw)
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
