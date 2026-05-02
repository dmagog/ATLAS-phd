"""Latency metrics (M3.C)."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import quantiles


@dataclass
class LatencyStats:
    n: int
    p50_ms: int
    p95_ms: int
    error_rate: float


def latency_stats(responses: list[dict]) -> LatencyStats:
    """p50, p95 и error_rate по логу runner'а."""
    latencies = [int(r.get("latency_ms", 0)) for r in responses if r.get("latency_ms") is not None]
    errors = [r for r in responses if r.get("error") or r.get("http_status", 0) != 200]
    n = len(responses)
    if not latencies:
        return LatencyStats(n=n, p50_ms=0, p95_ms=0, error_rate=1.0 if n else 0.0)
    sorted_lat = sorted(latencies)
    # quantiles требует n>=2; для n=1 возвращаем то значение
    if len(sorted_lat) >= 2:
        qs = quantiles(sorted_lat, n=20)  # 5%-quantiles → idx 9 = p50, idx 18 = p95
        p50 = int(qs[9])
        p95 = int(qs[18])
    else:
        p50 = sorted_lat[0]
        p95 = sorted_lat[0]
    return LatencyStats(
        n=n,
        p50_ms=p50,
        p95_ms=p95,
        error_rate=len(errors) / n if n else 0.0,
    )
