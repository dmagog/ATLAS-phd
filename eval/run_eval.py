#!/usr/bin/env python3
"""
ATLAS eval harness — измеряет KPI-A1, KPI-R1, KPI-R2.

Использование:
  python eval/run_eval.py --base-url http://localhost:8000 --token <jwt>

JWT можно получить через:
  curl -X POST http://localhost:8000/auth/login \\
       -H "Content-Type: application/json" \\
       -d '{"username":"<user>","password":"<pass>"}' | jq -r .access_token

Флаги:
  --suite routing   — только KPI-A1 (Planner routing)
  --suite qa        — только KPI-R1/R2 (Q&A answers/refusals)
  --suite all       — все наборы (по умолчанию)
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).parent
DATA_DIR = EVAL_DIR / "data"
RESULTS_DIR = EVAL_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# KPI thresholds из ТЗ
KPI_A1_THRESHOLD = 0.90   # Точность роутинга Planner
KPI_R1_THRESHOLD = 0.95   # Доля неотказных ответов с цитатами
KPI_R2_THRESHOLD = 0.85   # Корректные отказы на out-of-scope вопросах


def load_gold(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    if not path.exists():
        print(f"[WARN] Gold-файл не найден: {path}")
        return []
    with open(path) as f:
        return json.load(f)


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── KPI-A1: Точность роутинга Planner ─────────────────────────────────────────

def run_routing_suite(base_url: str, token: str, delay: float) -> dict:
    cases = load_gold("routing_gold.json")
    if not cases:
        return {}

    print(f"\n{'='*60}")
    print(f"KPI-A1  Точность роутинга Planner  (цель ≥ {KPI_A1_THRESHOLD:.0%})")
    print(f"{'='*60}")

    results = []
    for case in cases:
        try:
            resp = httpx.post(
                f"{base_url}/chat/message",
                headers=auth_headers(token),
                json={"message_text": case["message"]},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            actual_route = data.get("route", "")
            passed = actual_route == case["expected_route"]
            mark = "✓" if passed else "✗"
            print(f"  {mark} [{case['id']}] expected={case['expected_route']:12s} got={actual_route:12s}  {case['message'][:50]}")
            results.append({"id": case["id"], "passed": passed,
                            "expected": case["expected_route"], "actual": actual_route})
        except Exception as exc:
            print(f"  ! [{case['id']}] ОШИБКА: {exc}")
            results.append({"id": case["id"], "passed": False, "error": str(exc)})

        if delay > 0:
            time.sleep(delay)

    passed_count = sum(1 for r in results if r.get("passed"))
    accuracy = passed_count / len(results) if results else 0
    status = "PASS" if accuracy >= KPI_A1_THRESHOLD else "FAIL"
    print(f"\n  KPI-A1: {passed_count}/{len(results)} = {accuracy:.1%}  [{status}]")

    return {
        "kpi": "KPI-A1",
        "threshold": KPI_A1_THRESHOLD,
        "value": round(accuracy, 4),
        "passed_count": passed_count,
        "total": len(results),
        "status": status,
        "cases": results,
    }


# ── KPI-R1/R2: Q&A — ответы с цитатами и отказы ─────────────────────────────

def run_qa_suite(base_url: str, token: str, delay: float) -> dict:
    cases = load_gold("qa_gold.json")
    if not cases:
        return {}

    print(f"\n{'='*60}")
    print(f"KPI-R1  Ответы с цитатами        (цель ≥ {KPI_R1_THRESHOLD:.0%})")
    print(f"KPI-R2  Корректные отказы        (цель ≥ {KPI_R2_THRESHOLD:.0%})")
    print(f"{'='*60}")

    answerable_cases = [c for c in cases if c.get("expect_answer")]
    refusal_cases    = [c for c in cases if not c.get("expect_answer")]

    r1_results = []
    r2_results = []

    for case in cases:
        expect_answer = case.get("expect_answer", True)
        try:
            resp = httpx.post(
                f"{base_url}/qa/message",
                headers=auth_headers(token),
                json={"message_text": case["question"]},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            status  = data.get("status", "")
            has_cit = bool(data.get("citations"))

            if expect_answer:
                # KPI-R1: ответ + хотя бы одна цитата
                passed = status == "answered" and has_cit
                mark = "✓" if passed else "✗"
                note = "" if passed else f"  status={status} citations={has_cit}"
                print(f"  {mark} [R1][{case['id']}] {case['question'][:52]}{note}")
                r1_results.append({"id": case["id"], "passed": passed,
                                   "status": status, "has_citations": has_cit})
            else:
                # KPI-R2: система должна отказать
                passed = status == "refused"
                mark = "✓" if passed else "✗"
                note = "" if passed else f"  status={status} (ожидался отказ)"
                print(f"  {mark} [R2][{case['id']}] {case['question'][:52]}{note}")
                r2_results.append({"id": case["id"], "passed": passed, "status": status})

        except Exception as exc:
            print(f"  ! [{case['id']}] ОШИБКА: {exc}")
            if expect_answer:
                r1_results.append({"id": case["id"], "passed": False, "error": str(exc)})
            else:
                r2_results.append({"id": case["id"], "passed": False, "error": str(exc)})

        if delay > 0:
            time.sleep(delay)

    def kpi(results, threshold, label):
        if not results:
            return {"kpi": label, "status": "SKIP", "value": None}
        p = sum(1 for r in results if r.get("passed"))
        acc = p / len(results)
        st = "PASS" if acc >= threshold else "FAIL"
        print(f"\n  {label}: {p}/{len(results)} = {acc:.1%}  [{st}]")
        return {"kpi": label, "threshold": threshold, "value": round(acc, 4),
                "passed_count": p, "total": len(results), "status": st, "cases": results}

    r1 = kpi(r1_results, KPI_R1_THRESHOLD, "KPI-R1")
    r2 = kpi(r2_results, KPI_R2_THRESHOLD, "KPI-R2")
    return {"r1": r1, "r2": r2}


# ── Итоговый отчёт ────────────────────────────────────────────────────────────

def print_summary(report: dict) -> None:
    print(f"\n{'='*60}")
    print("ИТОГОВЫЙ ОТЧЁТ")
    print(f"{'='*60}")
    rows = []
    for key, val in report.items():
        if isinstance(val, dict) and "kpi" in val:
            rows.append(val)
        elif isinstance(val, dict):
            for v in val.values():
                if isinstance(v, dict) and "kpi" in v:
                    rows.append(v)
    for r in rows:
        if r.get("status") == "SKIP":
            print(f"  {r['kpi']:10s}  —      SKIP")
            continue
        pct = f"{r['value']:.1%}" if r.get("value") is not None else "—"
        thr = f"{r['threshold']:.0%}" if r.get("threshold") is not None else "—"
        print(f"  {r['kpi']:10s}  {pct:>6s}  (цель {thr})  [{r.get('status','?')}]")

    overall = all(
        r.get("status") in ("PASS", "SKIP")
        for r in rows
        if r.get("status") != "SKIP"
    )
    print(f"\n  Общий результат: {'✓ ВСЕ KPI ДОСТИГНУТЫ' if overall else '✗ ЧАСТЬ KPI НЕ ДОСТИГНУТА'}")


# ── Точка входа ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="ATLAS eval harness")
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="Базовый URL приложения")
    parser.add_argument("--token", required=True,
                        help="JWT access token (Bearer)")
    parser.add_argument("--suite", choices=["routing", "qa", "all"], default="all",
                        help="Какой набор запустить (по умолчанию: all)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Пауза между запросами в секундах (снижает нагрузку на LLM-API)")
    parser.add_argument("--out", help="Путь для сохранения JSON-отчёта (необязательно)")
    args = parser.parse_args()

    print(f"ATLAS eval harness  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL : {args.base_url}")
    print(f"Suite    : {args.suite}")
    print(f"Delay    : {args.delay}s")

    report: dict = {"run_at": datetime.now().isoformat(), "base_url": args.base_url}

    if args.suite in ("routing", "all"):
        report["routing"] = run_routing_suite(args.base_url, args.token, args.delay)

    if args.suite in ("qa", "all"):
        report["qa"] = run_qa_suite(args.base_url, args.token, args.delay)

    print_summary(report)

    # Сохранить отчёт
    out_path = Path(args.out) if args.out else RESULTS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  Отчёт сохранён: {out_path}")


if __name__ == "__main__":
    main()
