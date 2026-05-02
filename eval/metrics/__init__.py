"""Metrics package for ATLAS eval (M3.C).

Каждая метрика — отдельный модуль; main entrypoint — `eval/score.py`,
который агрегирует все метрики поверх `responses.jsonl` + golden set.

Модули:
- refusal.py    — refusal correctness (TNR/FNR), refusal reason precision
- latency.py    — p50/p95, error rate
- selfcheck.py  — rubric agreement (MAE, Cohen's kappa)
- faithfulness.py — LLM-judge (требует API key)
- citation.py   — embedding similarity (требует embedding service)
"""

from eval.metrics.refusal import refusal_correctness, refusal_reason_precision
from eval.metrics.latency import latency_stats
from eval.metrics.selfcheck import selfcheck_rubric_agreement

__all__ = [
    "refusal_correctness",
    "refusal_reason_precision",
    "latency_stats",
    "selfcheck_rubric_agreement",
]
