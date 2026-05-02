"""Refusal metrics (M3.C).

Две метрики:
1. Refusal correctness — на refusal-наборе TNR (true negative rate); на Q&A-наборе
   FNR (false negative rate, ложные отказы).
2. Refusal reason precision — когда отказали, по той ли причине.

Все вычисления — детерминированные, без внешних вызовов.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RefusalCorrectness:
    refusal_set_size: int
    refusal_set_correct: int  # система отказала, как и ожидалось
    qa_set_size: int
    qa_set_false_refusals: int  # система отказала, хотя должна была ответить

    @property
    def refusal_tnr(self) -> float:
        return self.refusal_set_correct / self.refusal_set_size if self.refusal_set_size else 0.0

    @property
    def qa_false_refusal_rate(self) -> float:
        return self.qa_set_false_refusals / self.qa_set_size if self.qa_set_size else 0.0


def _is_refusal(response: dict) -> bool:
    """Системно: считаем refusal'ом, если api_status == 'refused'."""
    return (response.get("api_status") or "").lower() == "refused"


def refusal_correctness(
    responses: list[dict], entries_by_id: dict[str, dict]
) -> RefusalCorrectness:
    """Сопоставляет responses с golden entries по `entry_id`/`type`/`expected_behavior`.

    Args:
        responses: распарсенные строки из responses.jsonl (dicts).
        entries_by_id: {entry.id: entry.model_dump()} от GoldenSetEntry.
    """
    refusal_size = 0
    refusal_correct = 0
    qa_size = 0
    qa_false_refusals = 0

    for r in responses:
        entry = entries_by_id.get(r["entry_id"])
        if entry is None:
            continue
        is_refusal = _is_refusal(r)
        expected_refuse = entry.get("expected_behavior") == "refuse"

        if expected_refuse:
            refusal_size += 1
            if is_refusal:
                refusal_correct += 1
        elif entry.get("expected_behavior") == "answer":
            qa_size += 1
            if is_refusal:
                qa_false_refusals += 1
        # self_check entries — пропускаем для refusal-метрики

    return RefusalCorrectness(
        refusal_set_size=refusal_size,
        refusal_set_correct=refusal_correct,
        qa_set_size=qa_size,
        qa_set_false_refusals=qa_false_refusals,
    )


def refusal_reason_precision(
    responses: list[dict], entries_by_id: dict[str, dict]
) -> tuple[int, int]:
    """Когда система отказала, попала ли причина в expected_refusal_reasons.

    Returns:
        (matched, total) — `total` = число фактических отказов, `matched` = из них
        с reason из expected_refusal_reasons. Score = matched / total.
    """
    matched = 0
    total = 0
    for r in responses:
        if not _is_refusal(r):
            continue
        entry = entries_by_id.get(r["entry_id"])
        if entry is None or entry.get("expected_behavior") != "refuse":
            continue
        total += 1
        actual_reason = (r.get("refusal_reason_code") or "").strip()
        expected = entry.get("expected_refusal_reasons", [])
        if actual_reason in expected:
            matched += 1
    return matched, total
