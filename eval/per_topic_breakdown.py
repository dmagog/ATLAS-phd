#!/usr/bin/env python3
"""per_topic_breakdown.py — per-topic срез метрик из eval run.

M4.5.E: eval-set v1.1 содержит `topic_external_id` для каждой не-refusal
entry. Этот скрипт принимает run-dir + golden-set и выдаёт breakdown:
сколько ответов / отказов / refusals / faithfulness / selfcheck по каждому
topic'у программы.

Usage:
    python3 eval/per_topic_breakdown.py \
        --run eval/results/m3c-reproducibility-treatment-20260506_190051 \
        --set eval/golden_set_v1/golden_set_v1.0.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--set", type=Path, required=True)
    args = p.parse_args(argv)

    entries = {}
    for line in args.set.open():
        e = json.loads(line)
        entries[e["id"]] = e

    rows = [json.loads(l) for l in (args.run / "responses.jsonl").open()]

    # Optional faithfulness detail
    faith_path = args.run / "faithfulness_detail.json"
    faith_by_id: dict[str, float] = {}
    if faith_path.exists():
        for rec in json.load(faith_path.open()):
            if rec.get("score") is not None and not rec.get("error"):
                faith_by_id[rec["entry_id"]] = float(rec["score"])

    # Aggregate per topic
    by_topic: dict[str, dict] = defaultdict(lambda: {
        "answered": 0, "refused": 0, "error": 0, "total": 0,
        "faithfulness_scores": [], "selfcheck_diffs": [],
        "by_type": defaultdict(int),
    })

    for r in rows:
        eid = r["entry_id"]
        e = entries.get(eid, {})
        if e.get("type") == "refusal":
            continue  # skip — refusal block has no topic
        tid = e.get("topic_external_id") or "(unmapped)"
        bucket = by_topic[tid]
        bucket["total"] += 1
        bucket["by_type"][e.get("type", "?")] += 1
        s = r.get("api_status")
        if s == "answered":
            bucket["answered"] += 1
        elif s == "refused":
            bucket["refused"] += 1
        elif s == "error" or r.get("error"):
            bucket["error"] += 1

        if eid in faith_by_id:
            bucket["faithfulness_scores"].append(faith_by_id[eid])

        if e.get("type") == "self_check" and r.get("sc_overall_score") is not None:
            diff = abs(float(e["expected_overall"]) - float(r["sc_overall_score"]))
            bucket["selfcheck_diffs"].append(diff)

    # Output
    print(f"# Per-topic breakdown — {args.run.name}\n")
    print(f"{'topic':<14} {'total':>5} {'ans':>4} {'ref':>4} {'err':>4}  "
          f"{'faith_n':>7} {'faith_μ':>8}  {'sc_n':>4} {'sc_MAE':>7}  types")

    for tid in sorted(by_topic):
        b = by_topic[tid]
        faith_n = len(b["faithfulness_scores"])
        faith_mu = statistics.mean(b["faithfulness_scores"]) if faith_n else None
        sc_n = len(b["selfcheck_diffs"])
        sc_mae = statistics.mean(b["selfcheck_diffs"]) if sc_n else None
        types_str = ",".join(f"{t}:{n}" for t, n in sorted(b["by_type"].items()))
        print(
            f"{tid:<14} {b['total']:>5} {b['answered']:>4} {b['refused']:>4} {b['error']:>4}  "
            f"{faith_n:>7} {f'{faith_mu:.3f}' if faith_mu is not None else '   —':>8}  "
            f"{sc_n:>4} {f'{sc_mae:.3f}' if sc_mae is not None else '   —':>7}  {types_str}"
        )

    # Roll-up
    total = sum(b["total"] for b in by_topic.values())
    answered = sum(b["answered"] for b in by_topic.values())
    refused = sum(b["refused"] for b in by_topic.values())
    error = sum(b["error"] for b in by_topic.values())
    all_faith = [s for b in by_topic.values() for s in b["faithfulness_scores"]]
    print(
        f"\n{'TOTAL':<14} {total:>5} {answered:>4} {refused:>4} {error:>4}  "
        f"{len(all_faith):>7} {f'{statistics.mean(all_faith):.3f}' if all_faith else '—':>8}"
    )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
