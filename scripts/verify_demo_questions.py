#!/usr/bin/env python3
"""verify_demo_questions.py — Phase 6.3.

Прогоняет demo-вопросы из demo_questions.json через работающий API
и проверяет, что каждый вопрос даёт ожидаемое поведение:
  * qa_questions_answered → status=answered + ≥ N citations
  * qa_questions_refusal  → status=refused
  * selfcheck_topics      → start возвращает 6 вопросов (LLM expensive,
    skip по умолчанию; --include-selfcheck для полного прогона)

Использование:
    docker compose exec -T app python3 /app/scripts/verify_demo_questions.py \\
        [--include-selfcheck] [--user EMAIL] [--password PASSWORD]

Default user: ivanov@optics.demo / demo (student, у него есть доступ к чату).

Скрипт безопасен (read-only после login). Он использует реальные LLM-
вызовы для qa_questions_answered (~5-30с/запрос), но НЕ для refusal
(hard-gate срабатывает до LLM). Self-check skip'ается по умолчанию.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx


BASE_URL = os.getenv("ATLAS_BASE_URL", "http://127.0.0.1:8731")
QUESTIONS_FILE = Path(__file__).parent / "demo_questions.json"


async def login(client: httpx.AsyncClient, email: str, password: str) -> str:
    res = await client.post("/auth/login", json={"email": email, "password": password})
    res.raise_for_status()
    return res.json()["access_token"]


async def ask(client: httpx.AsyncClient, token: str, query: str) -> dict:
    res = await client.post(
        "/chat/message",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"message_text": query, "response_profile": "detailed", "language": "ru", "conversation_history": []},
        timeout=60.0,
    )
    res.raise_for_status()
    return res.json()


async def selfcheck_start(client: httpx.AsyncClient, token: str, topic: str) -> dict:
    res = await client.post(
        "/self-check/start",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"topic": topic, "language": "ru"},
        timeout=120.0,
    )
    res.raise_for_status()
    return res.json()


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--user", default="ivanov@optics.demo")
    p.add_argument("--password", default=os.getenv("DEMO_PASSWORD", "demo"))
    p.add_argument("--include-selfcheck", action="store_true",
                   help="Also verify self-check generation (slow, expensive — LLM-heavy).")
    p.add_argument("--quick", action="store_true",
                   help="Test only ONE qa-answered + ONE refusal (smoke).")
    args = p.parse_args()

    data = json.loads(QUESTIONS_FILE.read_text())
    qa_answered = data["qa_questions_answered"]
    qa_refusal  = data["qa_questions_refusal"]
    sc_topics   = data["selfcheck_topics"]
    if args.quick:
        qa_answered = qa_answered[:1]
        qa_refusal  = qa_refusal[:1]

    failures: list[str] = []
    successes: list[str] = []

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        print(f"🔐 Logging in as {args.user} …")
        token = await login(client, args.user, args.password)
        print(f"  ✓ token acquired")
        print()

        # qa_answered
        print("─" * 64)
        print(f"A. qa_questions_answered ({len(qa_answered)})")
        print("─" * 64)
        for q in qa_answered:
            label = f"  {q['id']:25s}"
            try:
                r = await ask(client, token, q["query"])
                status = r.get("status")
                cites = len(r.get("citations") or [])
                if status == "answered" and cites >= q.get("expected_min_citations", 1):
                    print(f"{label} ✓ answered ({cites} citations)")
                    successes.append(q["id"])
                else:
                    msg = f"{label} ✗ status={status} citations={cites} (expected answered + ≥{q.get('expected_min_citations', 1)})"
                    print(msg)
                    failures.append(msg)
            except Exception as e:
                msg = f"{label} ✗ EXCEPTION {type(e).__name__}: {e}"
                print(msg)
                failures.append(msg)

        # qa_refusal
        print()
        print("─" * 64)
        print(f"B. qa_questions_refusal ({len(qa_refusal)})")
        print("─" * 64)
        for q in qa_refusal:
            label = f"  {q['id']:25s}"
            try:
                r = await ask(client, token, q["query"])
                status = r.get("status")
                if status in ("refused", "refusal"):
                    print(f"{label} ✓ refused (hard-gate сработал)")
                    successes.append(q["id"])
                else:
                    msg = f"{label} ✗ status={status} (expected refused) — hard-gate НЕ сработал!"
                    print(msg)
                    failures.append(msg)
            except Exception as e:
                msg = f"{label} ✗ EXCEPTION {type(e).__name__}: {e}"
                print(msg)
                failures.append(msg)

        # selfcheck (only if explicit)
        if args.include_selfcheck:
            print()
            print("─" * 64)
            print(f"C. selfcheck_topics ({len(sc_topics)}) — LLM-heavy, медленно")
            print("─" * 64)
            for q in sc_topics:
                label = f"  {q['id']:25s}"
                try:
                    r = await selfcheck_start(client, token, q["topic"])
                    n_q = len(r.get("questions") or [])
                    if n_q >= 4:
                        print(f"{label} ✓ generated {n_q} questions")
                        successes.append(q["id"])
                    else:
                        msg = f"{label} ✗ only {n_q} questions (expected ≥4)"
                        print(msg)
                        failures.append(msg)
                except Exception as e:
                    msg = f"{label} ✗ EXCEPTION {type(e).__name__}: {e}"
                    print(msg)
                    failures.append(msg)
        else:
            print()
            print("─" * 64)
            print(f"C. selfcheck_topics SKIPPED (use --include-selfcheck для прогона)")
            print("─" * 64)

    # Summary
    print()
    print("═" * 64)
    print(f"  ✓ {len(successes)} passed   ✗ {len(failures)} failed")
    print("═" * 64)
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
