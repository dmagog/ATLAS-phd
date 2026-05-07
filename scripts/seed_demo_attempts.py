#!/usr/bin/env python3
"""seed_demo_attempts.py — Phase 6.2.

Создаёт реалистичные self-check attempts для 12 demo-студентов в
optics-kafedra, чтобы supervisor heatmap был содержательным:
  * ~36-40 completed attempts (порог heatmap = 30)
  * Score-распределение спроектировано: разные студенты на разных
    уровнях, разные топики разной сложности, чтобы heatmap получился
    цветным (не все зелёный, не все красный)
  * evaluation JSON правдоподобен: overall_score, criterion_scores
    (по 4 критериям 40/30/20/10), evaluator_summary, error_tags,
    question_results

Используются deterministic-seed (random.seed(42)) — повторные запуски
дают идентичный набор данных. Идемпотентен: пропускает уже созданные
(user_id, topic_id) пары если evaluation.source == 'seed_demo_attempts'.

Для упрощения и независимости от LLM, question_set и evaluation —
hand-crafted фиктуры. Это OK потому что supervisor heatmap в принципе
не показывает текст ответов студентов (M5 privacy); агрегатам нужны
только overall_score и status.

Запуск:
    docker compose exec -T app python3 /app/scripts/seed_demo_attempts.py
"""
from __future__ import annotations

import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, "/app/src")

from atlas.db.models import Program, ProgramTopic, SelfCheckAttempt, SelfCheckStatus, Tenant, User, UserRole
from atlas.db.session import AsyncSessionLocal


TENANT_SLUG = "optics-kafedra"
SEED = 42


# Score-skill каждого студента (детерминирован). Дефолт: 0.6 (mid).
# Высокие/низкие профили распределены так, чтобы supervisor heatmap
# показывал реалистичный смесь зелёного / жёлтого / красного.
STUDENT_SKILL: dict[str, float] = {
    # high performers (4)
    "ivanov@optics.demo":      0.88,
    "kozlova@optics.demo":     0.85,
    "sokolov@optics.demo":     0.82,
    "petrova@optics.demo":     0.78,
    # mid (4)
    "egorov@optics.demo":      0.72,
    "morozov@optics.demo":     0.65,
    "zaytseva@optics.demo":    0.62,
    "sidorov@optics.demo":     0.58,
    # struggling (4)
    "volkov@optics.demo":      0.48,
    "lebedeva@optics.demo":    0.42,
    "raskolnikov@optics.demo": 0.35,
    "belyaev@optics.demo":     0.28,
}


# Topic difficulty multiplier (1.0 = neutral, < 1 = harder, > 1 = easier).
# Проектирует, что Дифракция/Поляризация — сложнее остальных.
TOPIC_DIFFICULTY: dict[str, float] = {
    "1.1": 1.05,  # Принципы Ферма и Гюйгенса — easy
    "1.2": 1.00,  # Тонкие линзы и зеркала
    "1.3": 0.95,  # Полное внутреннее отражение
    "2.1": 0.90,  # Интерференция света
    "2.2": 0.78,  # Дифракция Френеля и Фраунгофера — hardest
    "2.3": 0.85,  # Поляризация света — hard
}


# Сколько топиков пробовал каждый студент.
TOPIC_COUNTS: dict[str, int] = {
    # high performers пробуют больше
    "ivanov@optics.demo":      5,
    "kozlova@optics.demo":     6,
    "sokolov@optics.demo":     4,
    "petrova@optics.demo":     5,
    # mid — 3-4 попытки
    "egorov@optics.demo":      3,
    "morozov@optics.demo":     4,
    "zaytseva@optics.demo":    3,
    "sidorov@optics.demo":     2,  # реже занимается
    # struggling — 2-3
    "volkov@optics.demo":      3,
    "lebedeva@optics.demo":    2,
    "raskolnikov@optics.demo": 2,
    "belyaev@optics.demo":     1,  # начал недавно
}


# Per-criterion error templates по топикам.
ERROR_TAGS_BY_TOPIC: dict[str, list[str]] = {
    "1.1": ["принцип-Ферма", "Гюйгенс-волны", "оптический-путь"],
    "1.2": ["линзы-формула", "увеличение", "ход-лучей"],
    "1.3": ["критический-угол", "n-сред", "TIR"],
    "2.1": ["интерференция-условия", "когерентность", "разность-хода"],
    "2.2": ["дифракция-Френеля", "зоны-Френеля", "решётка"],
    "2.3": ["поляризация-Малюса", "брюстер", "двулучепреломление"],
}


SUMMARIES_GOOD = [
    "Студент уверенно владеет материалом, использует корректную терминологию и опирается на источники.",
    "Ответы полные и структурированные, лишь мелкие неточности в формулировках.",
    "Хороший уровень понимания, требуется лишь шлифовка нюансов.",
]
SUMMARIES_MID = [
    "Студент понимает основные идеи, но в деталях встречаются неточности; рекомендую освежить разделы программы.",
    "Удовлетворительное понимание; полнота снижена в открытых вопросах.",
    "Базовый уровень есть, нужна работа над терминологией и логической связностью.",
]
SUMMARIES_BAD = [
    "Студент путается в ключевых определениях; необходимо вернуться к учебнику и переработать тему.",
    "Преобладают ошибки в фактологии, рекомендуется очное занятие с преподавателем.",
    "Слабое понимание базовых принципов; требуется повторное изучение темы.",
]


def make_evaluation(rng: random.Random, overall: float, topic_id: str, n_questions: int = 6) -> dict:
    """Build a plausible-looking evaluation JSON consistent with overall score."""
    # Distribute around overall_score, perturb each criterion slightly.
    def jitter(x: float) -> float:
        return max(0.0, min(5.0, round(x + rng.uniform(-0.4, 0.4), 1)))

    cs = {
        "correctness":  jitter(overall),
        "completeness": jitter(overall - 0.2),
        "logic":        jitter(overall + 0.1),
        "terminology":  jitter(overall - 0.3),
    }
    if overall >= 4.0:
        summary = rng.choice(SUMMARIES_GOOD)
        n_tags = 1 if rng.random() < 0.4 else 0
    elif overall >= 2.5:
        summary = rng.choice(SUMMARIES_MID)
        n_tags = rng.randint(1, 3)
    else:
        summary = rng.choice(SUMMARIES_BAD)
        n_tags = rng.randint(2, 4)
    error_tags = rng.sample(ERROR_TAGS_BY_TOPIC[topic_id], min(n_tags, len(ERROR_TAGS_BY_TOPIC[topic_id])))

    # Build per-question results so the detail modal looks real.
    qrs = []
    for i in range(n_questions):
        is_mc = i < (n_questions - 2)
        if is_mc:
            correct = rng.random() < (overall / 5.0 + 0.05)
            qrs.append({
                "question_id": f"q-{i+1}",
                "type": "multiple_choice",
                "prompt": f"Вопрос {i+1} по теме (multiple choice)",
                "options": [
                    f"A) Вариант ответа A для вопроса {i+1}",
                    f"B) Вариант ответа B для вопроса {i+1}",
                    f"C) Вариант ответа C для вопроса {i+1}",
                    f"D) Вариант ответа D для вопроса {i+1}",
                ],
                "user_answer": "A" if correct else rng.choice(["B", "C", "D"]),
                "correct_answer": "A",
                "score": 1.0 if correct else 0.0,
                "status": "correct" if correct else "incorrect",
            })
        else:
            sc = jitter(overall)
            status = "correct" if sc >= 4.0 else "partial" if sc >= 2.5 else "incorrect"
            qrs.append({
                "question_id": f"q-{i+1}",
                "type": "open",
                "prompt": f"Вопрос {i+1} по теме (open-ended)",
                "user_answer": f"Развёрнутый ответ студента на вопрос {i+1}.",
                "score": sc,
                "status": status,
            })

    return {
        "overall_score": overall,
        "criterion_scores": cs,
        "evaluator_summary": summary,
        "error_tags": error_tags,
        "question_results": qrs,
        "source": "seed_demo_attempts",
    }


def make_question_set(topic_title: str, n: int = 6) -> list[dict]:
    """Опаковый question_set; supervisor heatmap его не использует."""
    return [
        {
            "question_id": f"q-{i+1}",
            "type": "multiple_choice" if i < (n - 2) else "open",
            "prompt": f"Вопрос {i+1} по теме «{topic_title}»",
            "options": [
                f"A) Вариант A",
                f"B) Вариант B",
                f"C) Вариант C",
                f"D) Вариант D",
            ] if i < (n - 2) else [],
        }
        for i in range(n)
    ]


def make_answers(qrs: list[dict]) -> list[dict]:
    return [{"question_id": qr["question_id"], "answer_text": qr.get("user_answer", "")} for qr in qrs]


async def seed() -> None:
    print(f"🌱 seed_demo_attempts.py — tenant={TENANT_SLUG}")
    rng = random.Random(SEED)

    async with AsyncSessionLocal() as db:
        tenant = (await db.execute(select(Tenant).where(Tenant.slug == TENANT_SLUG))).scalar_one_or_none()
        if not tenant:
            raise SystemExit(f"Tenant {TENANT_SLUG} not found")

        program = (await db.execute(
            select(Program).where(Program.tenant_id == tenant.id, Program.status == "active")
        )).scalar_one_or_none()
        if not program:
            raise SystemExit(f"Active program for {TENANT_SLUG} not found")

        topics = (await db.execute(
            select(ProgramTopic).where(ProgramTopic.program_id == program.id).order_by(ProgramTopic.ordinal)
        )).scalars().all()
        topic_by_ext = {t.external_id: t for t in topics}

        students = (await db.execute(
            select(User).where(
                User.tenant_id == tenant.id,
                User.role == UserRole.student.value,
                User.email.like("%@optics.demo"),
            )
        )).scalars().all()

        if len(students) < 12:
            print(f"⚠ Only {len(students)} demo students found; expected 12. Run seed_demo_users.py first.")

        print(f"  found {len(students)} students, {len(topics)} topics")
        print()

        created = 0
        skipped = 0
        now = datetime.utcnow()

        for student in students:
            skill = STUDENT_SKILL.get(student.email, 0.5)
            n_topics = TOPIC_COUNTS.get(student.email, 3)

            # Pick which topics this student tried (deterministic per email).
            ext_ids = sorted(topic_by_ext.keys())
            chosen_ids = rng.sample(ext_ids, min(n_topics, len(ext_ids)))

            for ext in chosen_ids:
                topic = topic_by_ext[ext]
                # Has already been seeded?
                exists = (await db.execute(
                    select(SelfCheckAttempt).where(
                        SelfCheckAttempt.user_id == student.id,
                        SelfCheckAttempt.topic_id == topic.id,
                    )
                )).scalars().first()
                if exists is not None and (exists.evaluation or {}).get("source") == "seed_demo_attempts":
                    skipped += 1
                    continue

                # Compute score.
                difficulty = TOPIC_DIFFICULTY.get(ext, 1.0)
                base = skill * difficulty * 5.0
                noise = rng.uniform(-0.6, 0.6)
                overall = max(0.5, min(5.0, round(base + noise, 1)))

                qset = make_question_set(topic.title)
                evaluation = make_evaluation(rng, overall, ext)
                answers = make_answers(evaluation["question_results"])

                # Created at a random time over the last 14 days, completed_at +1-15 min.
                created_at = now - timedelta(days=rng.randint(0, 14), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
                completed_at = created_at + timedelta(minutes=rng.randint(2, 15))

                attempt = SelfCheckAttempt(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    user_id=student.id,
                    topic=topic.title,
                    topic_id=topic.id,
                    language="ru",
                    status=SelfCheckStatus.completed.value,
                    question_set=qset,
                    answers=answers,
                    evaluation=evaluation,
                    created_at=created_at,
                    completed_at=completed_at,
                )
                db.add(attempt)
                created += 1
                print(f"  + {student.email:30s} · {ext} · score={overall}")

        await db.commit()
        print()
        print(f"✓ created: {created}")
        print(f"✓ skipped (already seeded): {skipped}")


if __name__ == "__main__":
    asyncio.run(seed())
