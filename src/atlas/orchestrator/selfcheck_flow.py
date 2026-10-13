"""
Self-check orchestration:
  start:  REQUEST_RECEIVED → SC_ATTEMPT_CREATED
  submit: SC_ANSWERS_SUBMITTED → SC_EVALUATED | INVALID_EVALUATION
"""
import asyncio
import random
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from atlas.core.logging import logger
from atlas.db.models import Program, ProgramTopic, SelfCheckAttempt
from atlas.llm.embeddings import get_embedding
from atlas.orchestrator.states import RequestState
from atlas.programs.study import study_prompt
from atlas.retriever.retriever import retrieve
from atlas.selfcheck.generator import (
    Question,
    QuestionSet,
    generate_multi_topic_questions,
    generate_question_set,
)
from atlas.selfcheck.evaluator import EvaluationPayload, evaluate_answers

# Длина теста → число вопросов. «short» = 3 MC + 2 open — на этом наборе
# валидирована рубрика (κ_binarized = 1.000), его не трогаем.
TEST_LENGTHS = {"short": 5, "medium": 10, "long": 20}
# Длинные наборы — порциями по 5 вопросов (3 MC + 2 open), параллельно.
# Замер на GigaChat-2-Pro: на 10 вопросов за вызов модель путала состав
# (8 MC / 12 open вместо 12 / 8) и типы, а один вызов на 10 шёл ~90 с;
# порция 5 — тот же состав, что у валидированного короткого теста.
_BATCH_SIZE = 5
_MC_SHARE = 0.6
# Тема попытки «по всей программе» — по префиксу её узнаёт фильтр истории.
FULL_PROGRAM_TOPIC_PREFIX = "Вся программа"


def _split_counts(n: int) -> tuple[int, int]:
    n_mc = round(n * _MC_SHARE)
    return n_mc, n - n_mc


def _batches(n: int) -> list[int]:
    sizes = []
    while n > 0:
        sizes.append(min(_BATCH_SIZE, n))
        n -= sizes[-1]
    return sizes


def _renumber(questions: list[Question]) -> list[Question]:
    for i, q in enumerate(questions, start=1):
        q.question_id = f"q{i}"
    return questions


async def _generate_single_topic(
    topic: str, n: int, context_chunks: list[str], language: str, request_id: str
) -> QuestionSet:
    sizes = _batches(n)
    if len(sizes) == 1:
        n_mc, n_open = _split_counts(n)
        return await generate_question_set(
            topic=topic, language=language, context_chunks=context_chunks,
            request_id=request_id, n_mc=n_mc, n_open=n_open,
        )
    # Порции получают разные фрагменты (через один), чтобы вопросы не повторялись.
    sets = await asyncio.gather(*[
        generate_question_set(
            topic=topic, language=language,
            context_chunks=context_chunks[i::len(sizes)] or context_chunks,
            request_id=request_id, n_mc=_split_counts(size)[0], n_open=_split_counts(size)[1],
        )
        for i, size in enumerate(sizes)
    ])
    questions = [q for qs in sets for q in qs.questions]
    return QuestionSet(topic=topic, language=language, questions=_renumber(questions))


def _program_topic_slots(topics: list[ProgramTopic], n: int) -> list[ProgramTopic]:
    """n слотов вопросов по темам: темы перемешаны внутри разделов, разделы
    чередуются — короткий тест захватывает все разделы, а не первые темы.
    Если тем меньше n, они повторяются по кругу."""
    by_section: dict[str, list[ProgramTopic]] = {}
    for t in topics:
        by_section.setdefault(t.section, []).append(t)
    for group in by_section.values():
        random.shuffle(group)
    order: list[ProgramTopic] = []
    while any(by_section.values()):
        for group in by_section.values():
            if group:
                order.append(group.pop())
    return [order[i % len(order)] for i in range(n)]


async def _generate_full_program(
    db: AsyncSession, tenant_id, n: int, language: str, request_id: str
) -> QuestionSet:
    program_id = (await db.execute(
        select(Program.id).where(Program.tenant_id == tenant_id, Program.status == "active")
    )).scalar_one_or_none()
    if program_id is None:
        raise ValueError("NO_ACTIVE_PROGRAM")
    topics = (await db.execute(
        select(ProgramTopic)
        .where(ProgramTopic.program_id == program_id, ProgramTopic.coverage_chunks > 0)
        .order_by(ProgramTopic.ordinal)
    )).scalars().all()
    if not topics:
        raise ValueError("NO_COVERED_TOPICS")

    slots = _program_topic_slots(list(topics), n)
    # Материалы по каждой теме — тем же запросом, что и подсказки в чате.
    chunks_by_topic: dict = {}
    for t in {t.id: t for t in slots}.values():
        query = study_prompt(t.title, t.section, t.key_concepts or [])
        r = await retrieve(
            query_embedding=await get_embedding(query, request_id=request_id),
            db=db, tenant_id=tenant_id, top_k=4, query_text=query, request_id=request_id,
        )
        chunks_by_topic[t.id] = [c.text for c in r.candidates[:3]]

    def label(t: ProgramTopic) -> str:
        return f"{t.external_id} {t.title}"

    jobs, start = [], 0
    for size in _batches(n):
        portion = slots[start:start + size]
        start += size
        counts: dict = {}
        for t in portion:
            counts[t.id] = counts.get(t.id, 0) + 1
        topic_args = [
            (label(t), counts[t.id], chunks_by_topic[t.id])
            for t in {t.id: t for t in portion}.values()
        ]
        n_mc, n_open = _split_counts(size)
        jobs.append(generate_multi_topic_questions(topic_args, n_mc, n_open, request_id))
    portions = await asyncio.gather(*jobs)
    questions = _renumber([q for qs in portions for q in qs])
    return QuestionSet(
        topic=f"{FULL_PROGRAM_TOPIC_PREFIX} · {len(questions)} вопросов",
        language=language,
        questions=questions,
    )


async def start_selfcheck(
    topic: str,
    user_id: str,
    tenant_id: "uuid.UUID",
    db: AsyncSession,
    language: str = "ru",
    request_id: str | None = None,
    topic_id: "uuid.UUID | None" = None,
    length: str = "short",
    full_program: bool = False,
) -> tuple[str, QuestionSet]:
    """topic_id — тема активной программы (если попытка начата по билету):
    по нему строятся фильтр истории и аналитика научрука. Для «своей темы» None.
    length — short/medium/long (TEST_LENGTHS). full_program — вопросы по всем
    темам программы вместо одной (topic игнорируется)."""
    request_id = request_id or str(uuid.uuid4())
    logger.info("sc_flow_start", state=RequestState.REQUEST_RECEIVED, request_id=request_id,
                length=length, full_program=full_program)
    n_questions = TEST_LENGTHS.get(length, TEST_LENGTHS["short"])

    if full_program:
        question_set = await _generate_full_program(db, tenant_id, n_questions, language, request_id)
        return await _save_attempt(db, tenant_id, user_id, question_set.topic, None,
                                   language, question_set, request_id)

    # Retrieve corpus chunks relevant to the topic (M4.B: tenant-scoped)
    query_embedding = await get_embedding(topic, request_id=request_id)
    retrieval = await retrieve(
        query_embedding=query_embedding,
        db=db,
        tenant_id=tenant_id,
        top_k=12,
        query_text=topic,
        request_id=request_id,
    )
    context_chunks = [c.text for c in retrieval.candidates]
    logger.info(
        "sc_flow_retrieval",
        chunks_found=len(context_chunks),
        enough_evidence=retrieval.enough_evidence,
        request_id=request_id,
    )

    question_set = await _generate_single_topic(
        topic, n_questions, context_chunks, language, request_id
    )
    return await _save_attempt(db, tenant_id, user_id, topic, topic_id,
                               language, question_set, request_id)


async def _save_attempt(
    db: AsyncSession, tenant_id, user_id, topic: str, topic_id,
    language: str, question_set: QuestionSet, request_id: str,
) -> tuple[str, QuestionSet]:
    attempt = SelfCheckAttempt(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        topic=topic,
        topic_id=topic_id,
        language=language,
        status="in_progress",
        question_set=[
            {
                "question_id": q.question_id,
                "type": q.type,
                "prompt": q.prompt,
                "options": q.options,
                "correct_option": q.correct_option,  # stored server-side, not sent to user during quiz
                "topic": q.topic,
            }
            for q in question_set.questions
        ],
    )
    db.add(attempt)
    await db.commit()

    logger.info("sc_flow_state", state=RequestState.SC_ATTEMPT_CREATED,
                attempt_id=str(attempt.id), request_id=request_id)
    return str(attempt.id), question_set


async def submit_selfcheck(
    attempt_id: str,
    answers: list[dict],
    db: AsyncSession,
    request_id: str | None = None,
    tenant_id=None,
    user_id=None,
) -> EvaluationPayload:
    """Применить ответы к существующей попытке self-check.

    tenant_id/user_id обязательны для bound-пользователей (защита от IDOR:
    студент tenant'а A не должен иметь возможность отправить ответы
    в попытку из tenant'а B, угадав UUID). Если переданы — фильтруем
    SelfCheckAttempt по обоим полям, и 'не нашли' возвращаем как
    ATTEMPT_NOT_FOUND (а не FORBIDDEN), чтобы не подтверждать факт
    существования чужой попытки.

    Если параметры опущены (legacy-вызовы из тестов / админских скриптов),
    фильтр по id остаётся прежним. Все боевые точки входа из API теперь
    обязаны передавать tenant_id+user_id.
    """
    request_id = request_id or str(uuid.uuid4())

    stmt = select(SelfCheckAttempt).where(SelfCheckAttempt.id == attempt_id)
    if tenant_id is not None:
        stmt = stmt.where(SelfCheckAttempt.tenant_id == tenant_id)
    if user_id is not None:
        stmt = stmt.where(SelfCheckAttempt.user_id == user_id)
    result = await db.execute(stmt)
    attempt = result.scalar_one_or_none()
    if not attempt:
        raise ValueError("ATTEMPT_NOT_FOUND")

    # Schema check_constraint допускает только in_progress/completed/abandoned/
    # invalid_evaluation. Раньше здесь было 'submitted', что валило INSERT с
    # IntegrityError. Семантически после submit'а до завершения evaluation'а
    # attempt всё ещё в работе → in_progress.
    attempt.status = "in_progress"
    attempt.answers = answers
    await db.commit()

    logger.info("sc_flow_state", state=RequestState.SC_ANSWERS_SUBMITTED,
                attempt_id=attempt_id, request_id=request_id)

    # Вопросы из сохранённого question_set вместе с correct_option: генератор
    # кладёт его туда при start, а оценщик для MC сравнивает ответ с ним
    # («Correct answer: X» в промпте). Без него LLM угадывал правильный вариант
    # сам и мог засчитать неверный ответ.
    from atlas.selfcheck.generator import Question
    questions = [
        Question(
            question_id=q["question_id"],
            type=q["type"],
            prompt=q["prompt"],
            options=q.get("options", []),
            correct_option=q.get("correct_option"),
            topic=q.get("topic"),
        )
        for q in (attempt.question_set or [])
    ]

    try:
        payload = await evaluate_answers(
            attempt_id=attempt_id,
            questions=questions,
            answers=answers,
            request_id=request_id,
        )
        # 'evaluated' тоже отсутствует в check_constraint — успешный финал =
        # 'completed'. Тесты M5 supervisor heatmap уже работают со status='completed'.
        attempt.status = "completed"
        attempt.evaluation = {
            "overall_score": payload.overall_score,
            "criterion_scores": {
                "correctness": payload.criterion_scores.correctness,
                "completeness": payload.criterion_scores.completeness,
                "logic": payload.criterion_scores.logic,
                "terminology": payload.criterion_scores.terminology,
            },
            "question_results": [
                {"question_id": r.question_id, "type": r.type, "score": r.score, "status": r.status}
                for r in payload.question_results
            ],
            "error_tags": payload.error_tags,
            "confidence": payload.confidence,
            "evaluator_summary": payload.evaluator_summary,
            "policy_flags": payload.policy_flags,
        }
        attempt.completed_at = datetime.utcnow()
        await db.commit()
        logger.info("sc_flow_state", state=RequestState.SC_EVALUATED,
                    attempt_id=attempt_id, request_id=request_id)
        return payload

    except Exception as exc:
        attempt.status = "invalid_evaluation"
        await db.commit()
        logger.error("sc_flow_state", state=RequestState.INVALID_EVALUATION,
                     error=str(exc), attempt_id=attempt_id, request_id=request_id)
        raise
