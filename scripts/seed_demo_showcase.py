#!/usr/bin/env python3
"""seed_demo_showcase.py — Phase 6 polish.

Добавляет 3 hand-crafted self-check attempts со «звёздными» scores 4.5+
для ivanov@optics.demo, чтобы supervisor drill-down имел кейс
«вот лучший студент кафедры». Покрывает топики, на которых ivanov ещё
не показывал высокий результат (2.1, 2.2, 2.3) — превращает его в
почти-полный hi-performer.

Запуск:
    docker compose exec -T app python3 /app/scripts/seed_demo_showcase.py

Идемпотентен: пропускает если evaluation.source == 'seed_demo_showcase'.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, "/app/src")

from atlas.db.models import Program, ProgramTopic, SelfCheckAttempt, SelfCheckStatus, Tenant, User
from atlas.db.session import AsyncSessionLocal


SHOWCASE_USER_EMAIL = "ivanov@optics.demo"

# (external_id, overall_score, days_ago, error_tags)
SHOWCASE_ATTEMPTS = [
    ("2.1", 4.7, 1, []),                           # interference — perfect
    ("2.2", 4.6, 3, ["дифракция-Френеля"]),        # difraction — strong with one minor flag
    ("2.3", 4.8, 6, []),                           # polarization — perfect
]


def make_evaluation(score: float, topic_extid: str, topic_title: str, error_tags: list[str]) -> dict:
    """Glamorous-but-plausible evaluation showing high consistent performance."""
    cs = {
        "correctness":  min(5.0, round(score + 0.1, 1)),
        "completeness": round(score - 0.1, 1),
        "logic":        min(5.0, round(score + 0.2, 1)),
        "terminology":  round(score - 0.2, 1),
    }
    summary_options = {
        4.6: "Студент свободно владеет материалом и корректно применяет терминологию. Незначительные шероховатости в полноте.",
        4.7: "Сильное и связное изложение, опирается на источники, ошибок не допускает.",
        4.8: "Отличное выполнение: высокая точность, полнота и логика. Терминология безупречна.",
    }
    summary = summary_options.get(score, summary_options[4.7])

    qrs = []
    for i in range(6):
        is_mc = i < 4
        if is_mc:
            qrs.append({
                "question_id": f"q-{i+1}",
                "type": "multiple_choice",
                "prompt": f"Контрольный вопрос {i+1} по теме «{topic_title}»",
                "options": [f"A) Корректное определение", f"B) Близкая, но неточная формулировка",
                            f"C) Распространённое заблуждение", f"D) Не относится к теме"],
                "user_answer": "A",
                "correct_answer": "A",
                "score": 1.0,
                "status": "correct",
            })
        else:
            qrs.append({
                "question_id": f"q-{i+1}",
                "type": "open",
                "prompt": f"Развёрнутый вопрос {i+1} по теме «{topic_title}»",
                "user_answer": "Студент дал полный, структурированный ответ с опорой на источники.",
                "score": min(5.0, round(score + 0.2, 1)),
                "status": "correct",
            })
    return {
        "overall_score": score,
        "criterion_scores": cs,
        "evaluator_summary": summary,
        "error_tags": error_tags,
        "question_results": qrs,
        "source": "seed_demo_showcase",
    }


def make_question_set(topic_title: str) -> list[dict]:
    return [
        {"question_id": f"q-{i+1}",
         "type": "multiple_choice" if i < 4 else "open",
         "prompt": f"Вопрос {i+1} по теме «{topic_title}»",
         "options": ["A) Корректное определение", "B) Близкая формулировка",
                     "C) Заблуждение", "D) Не по теме"] if i < 4 else []}
        for i in range(6)
    ]


async def seed() -> None:
    print(f"🌟 seed_demo_showcase — высокие scores для {SHOWCASE_USER_EMAIL}")
    print()

    async with AsyncSessionLocal() as db:
        user = (await db.execute(
            select(User).where(User.email == SHOWCASE_USER_EMAIL)
        )).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"User {SHOWCASE_USER_EMAIL} not found. Run seed_demo_users.py first.")

        tenant = (await db.execute(
            select(Tenant).where(Tenant.id == user.tenant_id)
        )).scalar_one_or_none()
        if tenant is None:
            raise SystemExit(f"Tenant for {SHOWCASE_USER_EMAIL} missing.")

        program = (await db.execute(
            select(Program).where(Program.tenant_id == tenant.id, Program.status == "active")
        )).scalar_one_or_none()
        if program is None:
            raise SystemExit("Active program not found.")

        topics = (await db.execute(
            select(ProgramTopic).where(ProgramTopic.program_id == program.id)
        )).scalars().all()
        topic_by_ext = {t.external_id: t for t in topics}

        now = datetime.utcnow()
        created = 0
        skipped = 0

        for ext, score, days_ago, error_tags in SHOWCASE_ATTEMPTS:
            topic = topic_by_ext.get(ext)
            if not topic:
                print(f"  ⚠ topic {ext} missing, skipping")
                continue

            # Idempotency: skip if a showcase attempt for this user+topic already exists.
            existing_showcase = (await db.execute(
                select(SelfCheckAttempt).where(
                    SelfCheckAttempt.user_id == user.id,
                    SelfCheckAttempt.topic_id == topic.id,
                )
            )).scalars().all()
            already = any(
                (a.evaluation or {}).get("source") == "seed_demo_showcase"
                for a in existing_showcase
            )
            if already:
                skipped += 1
                print(f"  ⊘ {ext} «{topic.title}» — showcase уже создан")
                continue

            evaluation = make_evaluation(score, ext, topic.title, error_tags)
            qset = make_question_set(topic.title)
            answers = [{"question_id": qr["question_id"], "answer_text": qr.get("user_answer", "")}
                       for qr in evaluation["question_results"]]

            created_at = now - timedelta(days=days_ago, hours=12)
            completed_at = created_at + timedelta(minutes=8)

            attempt = SelfCheckAttempt(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=user.id,
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
            print(f"  ✓ {ext} «{topic.title[:35]}» score={score} ({days_ago}d ago)")

        await db.commit()
        print()
        print(f"  created: {created}, skipped: {skipped}")


if __name__ == "__main__":
    asyncio.run(seed())
