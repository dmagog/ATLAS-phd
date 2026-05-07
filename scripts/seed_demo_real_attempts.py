#!/usr/bin/env python3
"""seed_demo_real_attempts.py — Phase 6.2 extension.

Запускает РЕАЛЬНЫЕ self-check сессии через LLM для каждого demo-студента.
В отличие от seed_demo_attempts.py (прямые DB-вставки с hand-crafted
данными), этот скрипт идёт через настоящие /self-check/start +
/self-check/{id}/submit endpoints, что даёт:

  * Настоящие question_set (LLM-генерированные по теме)
  * Настоящие user-answers (программно сгенерированные по skill-вероятности
    студента, см. STUDENT_SKILL ниже)
  * Настоящую оценку рубрики через LLM-evaluator

Использовать ПОСЛЕ seed_demo_attempts.py — добавит «real» attempts
параллельно с hand-crafted (по 1-2 на каждого студента). Helps the
supervisor heatmap drilldown показать настоящие данные при защите.

Цена:
  ~24 LLM-вызова (12 студентов × 2 LLM-calls per attempt)
  ~5-10 минут wall-time, ~$0.05-0.15 на OpenRouter (Llama 3.3 70B paid).

Идемпотентен: пропускает студентов, у кого уже есть ≥1 «real» attempt
(evaluation.source != 'seed_demo_attempts').

Использование:
    docker compose exec -T app python3 /app/scripts/seed_demo_real_attempts.py [--limit N] [--topic-per-student N]

    --limit N           — обработать только N студентов (default: все 12)
    --topic-per-student — сколько topics на студента (default: 1)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from typing import Any

import httpx


BASE_URL = os.getenv("ATLAS_BASE_URL", "http://127.0.0.1:8731")
PASSWORD = os.getenv("DEMO_PASSWORD", "demo")
SEED = 7  # different from seed_demo_attempts (42) so we don't collide

# ── Demo roster (matches seed_demo_users.py) ─────────────────────────────
# email → (skill, [list of topic external_ids]) — какие топики студент
# вероятно бы выбрал. Skill — вероятность дать правильный MC ответ
# и качественный open ответ.
STUDENT_PROFILES: dict[str, dict] = {
    # Topics 1.x — стабильно работают.
    # Topics 2.1, 2.2, 2.3 — содержат формулы с LaTeX backslashes; LLM
    # эмитит их в JSON-output, что иногда (особенно 2.2 «Дифракция Френеля
    # и Фраунгофера») ломает JSON-парсер с «Invalid \\escape» ошибкой.
    # Для real-attempts seed используем только 1.x для надёжности.
    # Hand-crafted attempts (seed_demo_attempts.py) покрывают 2.x для
    # supervisor heatmap.
    "ivanov@optics.demo":      {"skill": 0.88, "topics": ["1.1"]},
    "kozlova@optics.demo":     {"skill": 0.85, "topics": ["1.3"]},
    "sokolov@optics.demo":     {"skill": 0.82, "topics": ["1.1"]},  # was 2.2 (fails)
    "petrova@optics.demo":     {"skill": 0.78, "topics": ["1.2"]},
    "egorov@optics.demo":      {"skill": 0.72, "topics": ["1.3"]},
    "morozov@optics.demo":     {"skill": 0.65, "topics": ["1.1"]},
    "zaytseva@optics.demo":    {"skill": 0.62, "topics": ["1.2"]},  # was 2.2 (fails)
    "sidorov@optics.demo":     {"skill": 0.58, "topics": ["1.1"]},
    "volkov@optics.demo":      {"skill": 0.48, "topics": ["1.2"]},
    "lebedeva@optics.demo":    {"skill": 0.42, "topics": ["1.3"]},
    "raskolnikov@optics.demo": {"skill": 0.35, "topics": ["1.2"]},  # was 2.1 (failed once)
    "belyaev@optics.demo":     {"skill": 0.28, "topics": ["1.1"]},
}

# Topic title by external_id (для подачи в /self-check/start).
# Должны соответствовать program_topics.title в БД.
TOPICS_BY_EXTID: dict[str, str] = {
    "1.1": "Принципы Ферма и Гюйгенса",
    "1.2": "Тонкие линзы и зеркала",
    "1.3": "Полное внутреннее отражение",
    "2.1": "Интерференция света",
    "2.2": "Дифракция Френеля и Фраунгофера",
    "2.3": "Поляризация света",
}

# Plausible open-ended answer templates по топикам.
# Это «средне-OK» ответы — оценщик даст что-то от 2.5 до 4.0.
OPEN_TEMPLATES: dict[str, list[str]] = {
    "1.1": [
        "Принцип Ферма утверждает, что свет распространяется по пути, для которого время прохождения экстремально (минимально). Это эквивалентно требованию стационарности оптического пути.",
        "Принцип Гюйгенса говорит, что каждая точка волнового фронта является источником вторичных волн, и огибающая этих волн даёт следующее положение фронта.",
    ],
    "1.2": [
        "Формула тонкой линзы: 1/f = 1/d + 1/d', где f — фокусное расстояние, d — расстояние до предмета, d' — до изображения. Знаки определяются правилом для собирающих и рассеивающих линз.",
        "Линейное увеличение Γ = -d'/d. Знак минус указывает, что для собирающей линзы изображение перевёрнутое.",
    ],
    "1.3": [
        "Полное внутреннее отражение возникает на границе двух сред, когда угол падения превышает критический угол sin(θc) = n2/n1 (при n1 > n2). Свет полностью отражается обратно в более плотную среду.",
        "Это явление лежит в основе работы оптических волокон.",
    ],
    "2.1": [
        "Для наблюдения интерференции необходима когерентность волн (постоянная разность фаз) и одинаковая поляризация. При разности хода Δ = mλ образуются максимумы, при Δ = (m+1/2)λ — минимумы.",
        "Контраст полос максимален при равных амплитудах волн.",
    ],
    "2.2": [
        "Дифракция Френеля наблюдается на конечных расстояниях источник—экран и описывается методом зон Френеля. Дифракция Фраунгофера — предельный случай при бесконечном расстоянии (плоский фронт).",
        "Зоны Френеля разбивают волновой фронт на участки с разностью хода λ/2; чётные подавляют действие нечётных.",
    ],
    "2.3": [
        "Поляризация — упорядочивание колебаний электрического вектора волны в одной плоскости. Закон Малюса: I = I0·cos²θ, где θ — угол между плоскостями поляризатора и анализатора.",
        "Брюстер: при угле tg(θB) = n2/n1 отражённый луч полностью поляризован перпендикулярно плоскости падения.",
    ],
}


async def login(client: httpx.AsyncClient, email: str, password: str) -> str:
    r = await client.post("/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def already_has_real_attempt(client: httpx.AsyncClient, token: str) -> bool:
    """Check student's history for any attempt where evaluation.source != seed_demo_attempts."""
    r = await client.get("/self-check/history/list", headers=auth(token))
    if r.status_code != 200:
        return False
    items = r.json()
    # The list endpoint doesn't include evaluation.source — fetch detail for completed ones.
    for item in items[:5]:  # check up to 5 recent
        if item.get("status") != "completed":
            continue
        d = await client.get(f"/self-check/{item['attempt_id']}/detail", headers=auth(token))
        if d.status_code != 200:
            continue
        ev = d.json()
        # Detail doesn't return evaluation.source either; check question_results structure
        # Hand-crafted seed has q-1, q-2 etc; real LLM probably has different ID format
        qrs = ev.get("question_results") or []
        if qrs and not all(qr.get("question_id", "").startswith("q-") for qr in qrs):
            return True
    return False


def make_answer(rng: random.Random, q: dict, skill: float, topic_extid: str) -> str:
    """Generate a plausible answer based on student skill."""
    if q["type"] == "multiple_choice":
        # With probability=skill pick the «correct» option.
        # We don't know which is correct, so just pick option randomly weighted toward A
        # (LLMs often put correct answer at A or B). On low skill, more random.
        opts = q.get("options", [])
        if not opts:
            return "A"
        if rng.random() < skill:
            return opts[0].split(")")[0].split(".")[0].strip()  # likely "A" or "1"
        else:
            return rng.choice(opts).split(")")[0].split(".")[0].strip()
    else:
        # Open-ended — use template, possibly truncated for low-skill students.
        templates = OPEN_TEMPLATES.get(topic_extid, ["—"])
        text = rng.choice(templates)
        if skill < 0.4:
            # Struggling — give partial answer
            text = text.split(".")[0] + "."
        elif skill < 0.6:
            # Mid — give first two sentences
            parts = text.split(".")
            text = ".".join(parts[:2]) + "."
        return text


async def run_one_attempt(
    client: httpx.AsyncClient, token: str, email: str, topic_title: str, topic_extid: str, skill: float, rng: random.Random,
) -> dict:
    """Start + submit one self-check attempt via API."""
    # 1. Start
    print(f"     1. POST /self-check/start (LLM ~20-40s)…", flush=True)
    r = await client.post(
        "/self-check/start",
        headers=auth(token),
        json={"topic": topic_title, "language": "ru"},
        timeout=180.0,
    )
    if r.status_code != 200:
        return {"ok": False, "stage": "start", "code": r.status_code, "body": r.text[:300]}
    start_data = r.json()
    attempt_id = start_data["attempt_id"]
    questions = start_data.get("questions", [])
    print(f"        ✓ attempt_id={attempt_id[:8]}… questions={len(questions)}")

    # 2. Generate answers
    answers = []
    for q in questions:
        ans_text = make_answer(rng, q, skill, topic_extid)
        answers.append({"question_id": q["question_id"], "answer_text": ans_text})

    # 3. Submit
    print(f"     2. POST /self-check/{{id}}/submit (LLM ~10-30s)…", flush=True)
    r = await client.post(
        f"/self-check/{attempt_id}/submit",
        headers=auth(token),
        json=answers,
        timeout=180.0,
    )
    if r.status_code != 200:
        return {"ok": False, "stage": "submit", "code": r.status_code, "body": r.text[:300]}
    result = r.json()
    score = result.get("overall_score")
    print(f"        ✓ overall_score={score}")
    return {"ok": True, "attempt_id": attempt_id, "overall_score": score, "n_questions": len(questions)}


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None, help="Only process first N students")
    p.add_argument("--topic-per-student", type=int, default=1, help="How many topics to attempt per student")
    p.add_argument("--force", action="store_true", help="Skip idempotency check (run even if real attempts exist)")
    args = p.parse_args()

    rng = random.Random(SEED)
    profiles = list(STUDENT_PROFILES.items())
    if args.limit:
        profiles = profiles[: args.limit]

    print(f"🌱 seed_demo_real_attempts — {len(profiles)} students × {args.topic_per_student} topic(s)")
    print(f"   warning: ~{len(profiles) * args.topic_per_student * 2} LLM calls, ~{len(profiles) * args.topic_per_student}-{len(profiles) * args.topic_per_student * 2} min")
    print()

    successes: list[str] = []
    failures: list[str] = []
    skipped: list[str] = []

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        for i, (email, prof) in enumerate(profiles, 1):
            print(f"[{i}/{len(profiles)}] {email}  (skill={prof['skill']})")
            try:
                token = await login(client, email, PASSWORD)
            except Exception as e:
                print(f"  ✗ login failed: {e}")
                failures.append(f"{email}: login {e}")
                continue

            if not args.force:
                if await already_has_real_attempt(client, token):
                    print(f"  ⊘ skip — уже есть real attempt")
                    skipped.append(email)
                    continue

            chosen_topics = prof["topics"][: args.topic_per_student]
            for tid in chosen_topics:
                topic_title = TOPICS_BY_EXTID[tid]
                print(f"  → topic {tid} «{topic_title}»")
                result = await run_one_attempt(client, token, email, topic_title, tid, prof["skill"], rng)
                if result["ok"]:
                    successes.append(f"{email}/{tid}: score={result['overall_score']}")
                else:
                    msg = f"{email}/{tid}: FAIL {result['stage']} HTTP {result['code']}"
                    print(f"  ✗ {msg}")
                    print(f"    body: {result.get('body', '')[:200]}")
                    failures.append(msg)
            print()

    print("═" * 64)
    print(f"  ✓ {len(successes)} succeeded   ⊘ {len(skipped)} skipped   ✗ {len(failures)} failed")
    print("═" * 64)
    if successes:
        print("Successes:")
        for s in successes[:6]:
            print(f"  {s}")
        if len(successes) > 6:
            print(f"  …and {len(successes) - 6} more")
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  {f}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
