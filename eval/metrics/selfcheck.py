"""Self-check rubric agreement (M3.C).

MAE по 4 критериям + Cohen's kappa на binarized оценке (≥3 / <3).
"""

from __future__ import annotations

from dataclasses import dataclass

CRITERIA = ("correctness", "completeness", "logic", "terminology")


@dataclass
class RubricAgreement:
    n: int  # сколько self-check entries сравнено
    mae_per_criterion: dict[str, float]
    mae_overall: float
    kappa_binarized: float  # Cohen's kappa на bool(score >= 3)


def _cohen_kappa(y_true: list[int], y_pred: list[int]) -> float:
    """Cohen's kappa для бинарных меток. Возвращает 0 при недостатке данных."""
    n = len(y_true)
    if n == 0 or n != len(y_pred):
        return 0.0
    # Confusion: 2x2
    tp = sum(1 for a, b in zip(y_true, y_pred) if a == 1 and b == 1)
    tn = sum(1 for a, b in zip(y_true, y_pred) if a == 0 and b == 0)
    fp = sum(1 for a, b in zip(y_true, y_pred) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(y_true, y_pred) if a == 1 and b == 0)
    po = (tp + tn) / n
    p_yes = ((tp + fn) / n) * ((tp + fp) / n)
    p_no = ((tn + fp) / n) * ((tn + fn) / n)
    pe = p_yes + p_no
    if abs(1 - pe) < 1e-9:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def selfcheck_rubric_agreement(
    responses: list[dict], entries_by_id: dict[str, dict]
) -> RubricAgreement | None:
    """Сравнение system-оценок (sc_criterion_scores, sc_overall_score) с golden expected_*.

    Возвращает None если в ответах нет ни одной self-check записи (ничего сравнивать).
    """
    pairs = []
    for r in responses:
        entry = entries_by_id.get(r["entry_id"])
        if not entry or entry.get("type") != "self_check":
            continue
        if r.get("sc_criterion_scores") is None or r.get("sc_overall_score") is None:
            continue
        pairs.append(
            {
                "expected_overall": entry["expected_overall"],
                "actual_overall": r["sc_overall_score"],
                "expected_scores": entry["expected_scores"],
                "actual_scores": r["sc_criterion_scores"],
            }
        )

    if not pairs:
        return None

    mae_per_criterion: dict[str, float] = {}
    for c in CRITERIA:
        diffs = [
            abs(p["expected_scores"].get(c, 0.0) - p["actual_scores"].get(c, 0.0))
            for p in pairs
            if c in p["expected_scores"]
        ]
        mae_per_criterion[c] = sum(diffs) / len(diffs) if diffs else 0.0

    mae_overall = sum(abs(p["expected_overall"] - p["actual_overall"]) for p in pairs) / len(pairs)

    # Binarize: ≥3 → 1
    y_true = [1 if p["expected_overall"] >= 3 else 0 for p in pairs]
    y_pred = [1 if p["actual_overall"] >= 3 else 0 for p in pairs]
    kappa = _cohen_kappa(y_true, y_pred)

    return RubricAgreement(
        n=len(pairs),
        mae_per_criterion=mae_per_criterion,
        mae_overall=mae_overall,
        kappa_binarized=kappa,
    )
