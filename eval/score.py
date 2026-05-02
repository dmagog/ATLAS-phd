#!/usr/bin/env python3
"""ATLAS eval scorer (M3.C entrypoint).

Читает результат прогона runner'а (`responses.jsonl` + `run_meta.json`) и golden
set, вычисляет все метрики, пишет `summary.json` в ту же run-папку.

Использование:
    python eval/score.py \\
        --run eval/results/run-20260501_120000/ \\
        --set eval/golden_set_v1/golden_set_v1.0.jsonl \\
        [--judge-model openai/gpt-4o-mini] \\
        [--skip-judge]   # если нет API key или для smoke

Output (`summary.json`):
    {
      "config_name": ...,
      "metrics": {
        "refusal_correctness": {...},
        "refusal_reason_precision": {...},
        "latency": {...},
        "selfcheck_rubric": {...} | null,
        "faithfulness": {...} | null,
        "citation_accuracy": {...}
      }
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.metrics.refusal import refusal_correctness, refusal_reason_precision
from eval.metrics.latency import latency_stats
from eval.metrics.selfcheck import selfcheck_rubric_agreement
from eval.metrics.citation import citation_accuracy
from eval.metrics.faithfulness import faithfulness, judge_with_openrouter, judge_with_stub
from eval.schema import load_jsonl


def _read_responses(path: Path) -> list[dict]:
    out: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def score(run_dir: Path, set_path: Path, judge_model: str, skip_judge: bool) -> dict:
    responses_path = run_dir / "responses.jsonl"
    meta_path = run_dir / "run_meta.json"
    summary_path = run_dir / "summary.json"

    if not responses_path.exists():
        raise SystemExit(f"responses.jsonl not found in {run_dir}")
    responses = _read_responses(responses_path)
    entries = load_jsonl(set_path)
    entries_by_id = {e.id: e.model_dump() for e in entries}
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    print(f"[score] run={run_dir}  responses={len(responses)}  entries={len(entries)}")

    # 1. Refusal correctness (детерминированно, всегда работает)
    rc = refusal_correctness(responses, entries_by_id)
    rrp_matched, rrp_total = refusal_reason_precision(responses, entries_by_id)

    # 2. Latency
    lat = latency_stats(responses)

    # 3. Self-check rubric (None если в наборе нет self_check)
    sc = selfcheck_rubric_agreement(responses, entries_by_id)

    # 4. Citation accuracy (skeleton — пока 0)
    cit = citation_accuracy(responses, entries_by_id)

    # 5. Faithfulness (требует API key; можно skip)
    if skip_judge:
        faith = None
        print("[score] faithfulness: SKIPPED (--skip-judge)")
    else:
        try:
            faith = faithfulness(responses, entries_by_id, judge=judge_with_openrouter, model=judge_model)
            print(f"[score] faithfulness: judged={faith.n_judged}/{faith.n_responses}  mean={faith.mean_score:.3f}")
        except RuntimeError as e:
            print(f"[score] faithfulness: SKIPPED ({e})")
            faith = None

    summary = {
        "run_dir": str(run_dir),
        "config_name": meta.get("config_name"),
        "set_path": str(set_path),
        "n_responses": len(responses),
        "n_entries": len(entries),
        "metrics": {
            "refusal_correctness": {
                "refusal_set_size": rc.refusal_set_size,
                "refusal_set_correct": rc.refusal_set_correct,
                "refusal_tnr": round(rc.refusal_tnr, 4),
                "qa_set_size": rc.qa_set_size,
                "qa_set_false_refusals": rc.qa_set_false_refusals,
                "qa_false_refusal_rate": round(rc.qa_false_refusal_rate, 4),
            },
            "refusal_reason_precision": {
                "matched": rrp_matched,
                "total": rrp_total,
                "score": round(rrp_matched / rrp_total, 4) if rrp_total else None,
            },
            "latency": asdict(lat),
            "selfcheck_rubric": (
                {
                    "n": sc.n,
                    "mae_per_criterion": {k: round(v, 3) for k, v in sc.mae_per_criterion.items()},
                    "mae_overall": round(sc.mae_overall, 3),
                    "kappa_binarized": round(sc.kappa_binarized, 3),
                }
                if sc
                else None
            ),
            "faithfulness": (
                {
                    "n_responses": faith.n_responses,
                    "n_judged": faith.n_judged,
                    "mean_score": round(faith.mean_score, 4),
                    "judge_model": judge_model,
                }
                if faith
                else None
            ),
            "citation_accuracy": {
                "n_responses": cit.n_responses,
                "n_with_citations": cit.n_with_citations,
                "n_evaluated": cit.n_evaluated,
                "accuracy": round(cit.accuracy, 4),
                "note": "skeleton — full impl TBD (см. eval/metrics/citation.py)",
            },
        },
    }

    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[score] summary written: {summary_path}")

    # Детализация faithfulness — отдельный файл, чтобы не раздувать summary
    if faith and faith.per_response:
        detail_path = run_dir / "faithfulness_detail.json"
        detail_path.write_text(
            json.dumps(faith.per_response, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[score] faithfulness detail: {detail_path}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="ATLAS eval scorer (M3.C)")
    parser.add_argument("--run", type=Path, required=True, help="Run dir (output runner'а)")
    parser.add_argument("--set", type=Path, required=True, help="Golden set JSONL")
    parser.add_argument(
        "--judge-model",
        default="nvidia/nemotron-3-super-120b-a12b:free",
        help="LLM для faithfulness-судьи. Default — free; для production переключить на платную GPT-4-class.",
    )
    parser.add_argument(
        "--skip-judge", action="store_true", help="Не вызывать LLM-judge (для smoke без API key)"
    )
    args = parser.parse_args()
    score(args.run, args.set, args.judge_model, args.skip_judge)


if __name__ == "__main__":
    main()
