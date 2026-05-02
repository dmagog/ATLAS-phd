#!/usr/bin/env python3
"""ATLAS eval report generator (M3.E).

Берёт `summary.json` от treatment-прогона (опционально + baseline-прогон) и
генерирует markdown-отчёт `M3-report.md`. Если оба прогона есть — формирует
A/B-сравнение с дельтами.

Использование:
    # Только treatment
    python eval/report.py \\
        --treatment eval/results/run-treatment-20260501/

    # A/B
    python eval/report.py \\
        --treatment eval/results/run-treatment-20260501/ \\
        --baseline eval/results/run-baseline-20260501/ \\
        --out eval/results/M3-report.md

Output: M3-report.md с таблицами baseline / treatment / delta + интерпретацией.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


def _load_summary(run_dir: Path) -> dict:
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise SystemExit(f"summary.json not found in {run_dir} — run eval/score.py first")
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _fmt_pct(x: float | None) -> str:
    return f"{x:.1%}" if x is not None else "—"


def _fmt_float(x: float | None, digits: int = 3) -> str:
    return f"{x:.{digits}f}" if x is not None else "—"


def _fmt_delta_pct(t: float | None, b: float | None) -> str:
    if t is None or b is None:
        return "—"
    d = t - b
    sign = "+" if d >= 0 else ""
    return f"{sign}{d * 100:.1f} pp"


def _fmt_delta_ms(t: int | None, b: int | None) -> str:
    if t is None or b is None:
        return "—"
    d = t - b
    sign = "+" if d >= 0 else ""
    return f"{sign}{d} ms"


def _section_metrics_table(t: dict, b: dict | None) -> list[str]:
    tm = t["metrics"]
    bm = (b or {}).get("metrics", {})
    rows: list[str] = []

    if b is not None:
        rows.append("| Метрика | Baseline | Treatment | Δ |")
        rows.append("|---|---|---|---|")
    else:
        rows.append("| Метрика | Treatment |")
        rows.append("|---|---|")

    # Refusal correctness
    rc_t = tm["refusal_correctness"]
    rc_b = bm.get("refusal_correctness")
    if b is not None:
        rows.append(
            f"| Refusal TNR (правильные отказы на refusal-наборе) "
            f"| {_fmt_pct((rc_b or {}).get('refusal_tnr'))} "
            f"| {_fmt_pct(rc_t['refusal_tnr'])} "
            f"| {_fmt_delta_pct(rc_t['refusal_tnr'], (rc_b or {}).get('refusal_tnr'))} |"
        )
        rows.append(
            f"| Q&A False Refusal Rate (ложные отказы) "
            f"| {_fmt_pct((rc_b or {}).get('qa_false_refusal_rate'))} "
            f"| {_fmt_pct(rc_t['qa_false_refusal_rate'])} "
            f"| {_fmt_delta_pct(rc_t['qa_false_refusal_rate'], (rc_b or {}).get('qa_false_refusal_rate'))} |"
        )
    else:
        rows.append(f"| Refusal TNR | {_fmt_pct(rc_t['refusal_tnr'])} |")
        rows.append(f"| Q&A False Refusal Rate | {_fmt_pct(rc_t['qa_false_refusal_rate'])} |")

    # Refusal reason precision
    rrp_t = tm["refusal_reason_precision"]
    rrp_b = bm.get("refusal_reason_precision", {})
    if b is not None:
        rows.append(
            f"| Refusal reason precision "
            f"| {_fmt_pct(rrp_b.get('score'))} "
            f"| {_fmt_pct(rrp_t['score'])} "
            f"| {_fmt_delta_pct(rrp_t['score'], rrp_b.get('score'))} |"
        )
    else:
        rows.append(f"| Refusal reason precision | {_fmt_pct(rrp_t['score'])} |")

    # Faithfulness
    fa_t = tm.get("faithfulness")
    fa_b = bm.get("faithfulness")
    if fa_t is not None or fa_b is not None:
        if b is not None:
            rows.append(
                f"| Faithfulness (LLM-judge) "
                f"| {_fmt_float((fa_b or {}).get('mean_score')) if fa_b else '—'} "
                f"| {_fmt_float(fa_t['mean_score']) if fa_t else '—'} "
                f"| {_fmt_delta_pct((fa_t or {}).get('mean_score'), (fa_b or {}).get('mean_score'))} |"
            )
        else:
            rows.append(
                f"| Faithfulness (LLM-judge) "
                f"| {_fmt_float(fa_t['mean_score']) if fa_t else '— (skipped)'} |"
            )

    # Latency
    lat_t = tm["latency"]
    lat_b = bm.get("latency", {})
    if b is not None:
        rows.append(
            f"| Latency p50 "
            f"| {lat_b.get('p50_ms', '—')} ms "
            f"| {lat_t['p50_ms']} ms "
            f"| {_fmt_delta_ms(lat_t['p50_ms'], lat_b.get('p50_ms'))} |"
        )
        rows.append(
            f"| Latency p95 "
            f"| {lat_b.get('p95_ms', '—')} ms "
            f"| {lat_t['p95_ms']} ms "
            f"| {_fmt_delta_ms(lat_t['p95_ms'], lat_b.get('p95_ms'))} |"
        )
        rows.append(
            f"| Error rate "
            f"| {_fmt_pct(lat_b.get('error_rate'))} "
            f"| {_fmt_pct(lat_t['error_rate'])} "
            f"| {_fmt_delta_pct(lat_t['error_rate'], lat_b.get('error_rate'))} |"
        )
    else:
        rows.append(f"| Latency p50 | {lat_t['p50_ms']} ms |")
        rows.append(f"| Latency p95 | {lat_t['p95_ms']} ms |")
        rows.append(f"| Error rate | {_fmt_pct(lat_t['error_rate'])} |")

    # Self-check rubric (если есть)
    sc_t = tm.get("selfcheck_rubric")
    sc_b = bm.get("selfcheck_rubric")
    if sc_t or sc_b:
        if b is not None:
            rows.append(
                f"| Self-check MAE (overall) "
                f"| {_fmt_float((sc_b or {}).get('mae_overall'))} "
                f"| {_fmt_float(sc_t['mae_overall']) if sc_t else '—'} "
                f"| — |"
            )
        else:
            rows.append(f"| Self-check MAE (overall) | {_fmt_float(sc_t['mae_overall']) if sc_t else '— (no self-check entries)'} |")

    return rows


def _section_targets() -> list[str]:
    return [
        "## Стартовые таргеты (BDD 6.1)",
        "",
        "| Метрика | Floor | Stretch |",
        "|---|---|---|",
        "| Faithfulness (Q&A блок) | ≥ 0.65 | ≥ 0.80 |",
        "| Citation accuracy | ≥ 0.80 | ≥ 0.90 |",
        "| Refusal precision (refusal-набор) | ≥ 0.80 | ≥ 0.90 |",
        "| False refusal rate (Q&A блок) | ≤ 0.20 | ≤ 0.10 |",
        "| Self-check rubric MAE | ≤ 1.2 | ≤ 0.8 |",
        "| Latency p95 | ≤ 15 s | ≤ 10 s |",
        "",
        "Floor — нижний порог запуска пилота. Stretch — целевые цифры post-M6.",
    ]


def _section_interpretation(t: dict, b: dict | None) -> list[str]:
    rows = ["## Интерпретация", ""]
    tm = t["metrics"]
    rc = tm["refusal_correctness"]

    if b is not None:
        bm = b["metrics"]
        bc = bm["refusal_correctness"]
        delta_tnr = rc["refusal_tnr"] - bc["refusal_tnr"]
        delta_far = bc["qa_false_refusal_rate"] - rc["qa_false_refusal_rate"]
        rows.append(
            f"- **Вклад агентного контура** (treatment vs baseline): "
            f"refusal TNR {'+' if delta_tnr >= 0 else ''}{delta_tnr * 100:.1f} pp, "
            f"снижение ложных отказов {'+' if delta_far >= 0 else ''}{delta_far * 100:.1f} pp."
        )
        if tm.get("faithfulness") and bm.get("faithfulness"):
            d = tm["faithfulness"]["mean_score"] - bm["faithfulness"]["mean_score"]
            rows.append(
                f"- **Faithfulness**: treatment {tm['faithfulness']['mean_score']:.3f} vs "
                f"baseline {bm['faithfulness']['mean_score']:.3f} "
                f"({'+' if d >= 0 else ''}{d * 100:.1f} pp)."
            )
        lat_b = bm["latency"]["p95_ms"]
        lat_t = tm["latency"]["p95_ms"]
        rows.append(
            f"- **Цена контура**: latency p95 +{lat_t - lat_b} ms "
            f"({(lat_t - lat_b) / max(lat_b, 1) * 100:.0f}% над baseline)."
        )
    else:
        rows.append(
            "- Только treatment-прогон. Для defense-цифры «вклад агентного контура» "
            "нужен baseline-прогон (`eval/configs/baseline.toml`)."
        )

    # Sanity
    if rc["refusal_set_size"] == 0:
        rows.append("- ⚠ В наборе нет refusal-entries — TNR не репрезентативно.")
    if rc["qa_set_size"] < 30:
        rows.append(
            f"- ⚠ Q&A блок маленький ({rc['qa_set_size']} entries) — "
            f"false refusal rate с большим CI."
        )
    if tm.get("faithfulness") is None:
        rows.append("- ⚠ Faithfulness skipped — запустите `score.py` без `--skip-judge`.")

    return rows


def _section_examples(t: dict) -> list[str]:
    """Извлечь 3-5 «красноречивых» примеров — недоступно из summary.json напрямую,
    нужно читать responses.jsonl. Пока — placeholder."""
    return [
        "## Красноречивые примеры",
        "",
        "_Заполняется вручную после прогона: 3–5 примеров отказов / удачных ответов "
        "/ деградаций для defense-демо. Источник — `responses.jsonl` + `trace/{id}.json`._",
        "",
    ]


def _section_known_limitations(t: dict, b: dict | None) -> list[str]:
    rows = ["## Известные ограничения", ""]
    tm = t["metrics"]

    if tm["citation_accuracy"]["n_evaluated"] == 0:
        rows.append("- **Citation accuracy** — skeleton; полная имплементация требует подключения embedding-сервиса (см. `eval/metrics/citation.py`).")
    if t.get("n_responses", 0) < 50:
        rows.append(f"- **Размер прогона** — {t.get('n_responses')} responses; до полного v1.0 (120) — см. `eval/golden_set_v1/README.md`.")
    if tm.get("selfcheck_rubric") is None:
        rows.append("- **Self-check rubric agreement** — пока 0 self-check entries в golden set, метрика не вычислялась.")
    if tm.get("faithfulness") is None:
        rows.append("- **Faithfulness** — не запущена в этом прогоне.")
    rows.append("- **Refusal-набор маленький** — 3 entries в v1.0-draft; нужно расширение до 20.")

    return rows


def generate(
    treatment_dir: Path,
    baseline_dir: Path | None,
    out_path: Path,
) -> None:
    t = _load_summary(treatment_dir)
    b = _load_summary(baseline_dir) if baseline_dir else None

    lines: list[str] = []
    lines.append(f"# M3 Eval Report")
    lines.append("")
    lines.append(f"**Сгенерировано:** {datetime.utcnow().isoformat()}Z")
    lines.append(f"**Treatment:** `{treatment_dir}` ({t.get('config_name')})")
    if b:
        lines.append(f"**Baseline:** `{baseline_dir}` ({b.get('config_name')})")
    lines.append(f"**Golden set:** `{t['set_path']}` ({t['n_entries']} entries, {t['n_responses']} responses)")
    lines.append("")

    lines.append("## Сводка метрик")
    lines.append("")
    lines.extend(_section_metrics_table(t, b))
    lines.append("")
    lines.extend(_section_targets())
    lines.append("")
    lines.extend(_section_interpretation(t, b))
    lines.append("")
    lines.extend(_section_examples(t))
    lines.extend(_section_known_limitations(t, b))
    lines.append("")
    lines.append("## Воспроизводимость")
    lines.append("")
    lines.append("```bash")
    lines.append(f"# Treatment")
    lines.append(f"python eval/runner.py --set {t['set_path']} \\")
    lines.append(f"    --config eval/configs/treatment.toml --output {treatment_dir}")
    lines.append(f"python eval/score.py --run {treatment_dir} --set {t['set_path']}")
    if b:
        lines.append(f"")
        lines.append(f"# Baseline")
        lines.append(f"python eval/runner.py --set {t['set_path']} \\")
        lines.append(f"    --config eval/configs/baseline.toml --output {baseline_dir}")
        lines.append(f"python eval/score.py --run {baseline_dir} --set {t['set_path']}")
    lines.append("```")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[report] generated: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ATLAS M3 eval report generator")
    parser.add_argument("--treatment", type=Path, required=True, help="Treatment run dir")
    parser.add_argument("--baseline", type=Path, help="Baseline run dir (optional)")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("eval/results/M3-report.md"),
        help="Куда писать markdown",
    )
    args = parser.parse_args()
    generate(args.treatment, args.baseline, args.out)


if __name__ == "__main__":
    main()
