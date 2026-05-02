#!/usr/bin/env python3
"""ATLAS eval runner (M3.B).

Прогоняет golden set через публичный API ATLAS, логирует responses, citations,
retrieval traces, latency. Метрики (faithfulness, citation accuracy, etc.)
вычисляются отдельным шагом в `eval/metrics.py` (M3.C).

Архитектурное решение: runner ходит через **публичный API** (/qa/message,
/selfcheck/*), не через внутренние модули. Это даёт честную end-to-end картину
включая сериализацию, auth, валидацию.

Использование:
    python eval/runner.py \\
        --set eval/golden_set_v1/golden_set_v1.0.jsonl \\
        --config eval/configs/treatment.toml \\
        --output eval/results/run-{timestamp}/

Конфиг (TOML, минимум):
    name = "treatment"
    base_url = "http://localhost:8731"
    delay_seconds = 0.5
    timeout_seconds = 60
    # ATLAS_EVAL_TOKEN читается из ENV

Output:
    responses.jsonl   — одна запись на entry с финальным ответом + metadata
    trace/{id}.json   — per-query сырой response для отладки
    run_meta.json     — параметры прогона (config, sha, timestamp)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

# Добавляем корень репо в path, чтобы импортировать eval/schema.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.schema import (  # noqa: E402
    GoldenSetEntry,
    QAEntry,
    RefusalEntry,
    FormulaEntry,
    SelfCheckEntry,
    load_jsonl,
    summary,
)


# ── Config ────────────────────────────────────────────────────────────────────


@dataclass
class RunnerConfig:
    name: str
    base_url: str
    mode: str = "treatment"  # "treatment" | "baseline" (см. eval/configs/README.md)
    delay_seconds: float = 0.5
    timeout_seconds: int = 60
    token: str = ""  # filled from ENV at startup

    @classmethod
    def load(cls, path: Path, token_env: str = "ATLAS_EVAL_TOKEN") -> "RunnerConfig":
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        token = os.environ.get(token_env, "")
        if not token:
            raise SystemExit(
                f"ATLAS eval token not found. Set ${token_env} or pass --token."
            )
        return cls(
            name=raw.get("name", path.stem),
            base_url=raw["base_url"],
            mode=raw.get("mode", "treatment"),
            delay_seconds=raw.get("delay_seconds", 0.5),
            timeout_seconds=raw.get("timeout_seconds", 60),
            token=token,
        )


# ── Per-entry call dispatchers ────────────────────────────────────────────────


@dataclass
class RunResponse:
    """One response record written to responses.jsonl."""

    entry_id: str
    entry_type: str
    config_name: str
    started_at: str
    latency_ms: int
    http_status: int
    error: str | None = None
    # API-specific fields below — populated per type
    api_status: str | None = None  # "answered" / "refused" / "error"
    citations: list[dict] = None  # from /qa/message response
    refusal_reason_code: str | None = None  # ATLAS RefusalReasonCode enum
    answer_text: str | None = None  # answer_markdown в API
    request_id: str | None = None
    # Self-check specific
    sc_attempt_id: str | None = None
    sc_overall_score: float | None = None
    sc_criterion_scores: dict[str, float] | None = None
    sc_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None or k in {"error"}}


def _auth_headers(cfg: RunnerConfig) -> dict[str, str]:
    """Auth + eval-mode header. Backend смотрит на X-ATLAS-Eval-Mode при mode=baseline,
    чтобы пропустить verifier и self-check generator (см. eval/configs/README.md).
    """
    return {
        "Authorization": f"Bearer {cfg.token}",
        "Content-Type": "application/json",
        "X-ATLAS-Eval-Mode": cfg.mode,
    }


def call_qa(
    client: httpx.Client, cfg: RunnerConfig, entry: QAEntry | FormulaEntry | RefusalEntry
) -> tuple[RunResponse, dict | None]:
    """Call POST /qa/message. Returns (compact response, raw response dict)."""
    started = datetime.utcnow()
    t0 = time.monotonic()
    try:
        resp = client.post(
            f"{cfg.base_url}/qa/message",
            headers=_auth_headers(cfg),
            json={"message_text": entry.query},
            timeout=cfg.timeout_seconds,
        )
        latency = int((time.monotonic() - t0) * 1000)
        raw = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None
        rr = RunResponse(
            entry_id=entry.id,
            entry_type=entry.type,
            config_name=cfg.name,
            started_at=started.isoformat() + "Z",
            latency_ms=latency,
            http_status=resp.status_code,
            api_status=(raw or {}).get("status"),
            citations=(raw or {}).get("citations"),
            refusal_reason_code=(raw or {}).get("refusal_reason_code"),
            answer_text=(raw or {}).get("answer_markdown") or (raw or {}).get("answer_text"),
            request_id=(raw or {}).get("request_id") or resp.headers.get("x-request-id"),
        )
        if resp.status_code >= 400:
            rr.error = f"http {resp.status_code}: {resp.text[:200]}"
        return rr, raw
    except httpx.HTTPError as e:
        latency = int((time.monotonic() - t0) * 1000)
        return (
            RunResponse(
                entry_id=entry.id,
                entry_type=entry.type,
                config_name=cfg.name,
                started_at=started.isoformat() + "Z",
                latency_ms=latency,
                http_status=0,
                error=f"transport: {type(e).__name__}: {e}",
            ),
            None,
        )


def call_self_check(
    client: httpx.Client, cfg: RunnerConfig, entry: SelfCheckEntry
) -> tuple[RunResponse, dict | None]:
    """Self-check: start attempt with topic, submit canned user_answer, capture scores.

    NOTE: текущий /selfcheck/start API генерирует свои вопросы по теме. Чтобы
    тестировать ТОЛЬКО Evaluator (с canned_question + user_answer), потребуется
    либо расширить API debug-эндпоинтом `/selfcheck/evaluate`, либо подставлять
    user_answer на сгенерированный вопрос. Для skeleton M3.B — стартуем attempt
    и сабмитим user_answer как ответ на первый сгенерированный вопрос.
    Полная инструментовка — в follow-up.
    """
    started = datetime.utcnow()
    t0 = time.monotonic()
    try:
        # Start
        start_resp = client.post(
            f"{cfg.base_url}/selfcheck/start",
            headers=_auth_headers(cfg),
            json={"topic": entry.topic},
            timeout=cfg.timeout_seconds,
        )
        start_resp.raise_for_status()
        start = start_resp.json()
        attempt_id = start.get("attempt_id") or start.get("id")
        questions = start.get("questions", [])
        # Submit: ставим user_answer на ВСЕ вопросы для smoke; реальная логика
        # будет различать MC/open в follow-up.
        answers = [{"question_id": q.get("id"), "answer": entry.user_answer} for q in questions]
        submit_resp = client.post(
            f"{cfg.base_url}/selfcheck/{attempt_id}/submit",
            headers=_auth_headers(cfg),
            json={"answers": answers},
            timeout=cfg.timeout_seconds,
        )
        submit_resp.raise_for_status()
        result = submit_resp.json()
        latency = int((time.monotonic() - t0) * 1000)
        return (
            RunResponse(
                entry_id=entry.id,
                entry_type=entry.type,
                config_name=cfg.name,
                started_at=started.isoformat() + "Z",
                latency_ms=latency,
                http_status=submit_resp.status_code,
                sc_attempt_id=attempt_id,
                sc_status=result.get("status"),
                sc_overall_score=result.get("overall_score"),
                sc_criterion_scores=result.get("criterion_scores"),
            ),
            {"start": start, "submit": result},
        )
    except httpx.HTTPError as e:
        latency = int((time.monotonic() - t0) * 1000)
        return (
            RunResponse(
                entry_id=entry.id,
                entry_type=entry.type,
                config_name=cfg.name,
                started_at=started.isoformat() + "Z",
                latency_ms=latency,
                http_status=0,
                error=f"transport: {type(e).__name__}: {e}",
            ),
            None,
        )


def run_entry(
    client: httpx.Client, cfg: RunnerConfig, entry: GoldenSetEntry
) -> tuple[RunResponse, dict | None]:
    """Dispatch to the right caller based on entry.type."""
    if entry.type in ("qa", "formula", "refusal"):
        return call_qa(client, cfg, entry)  # type: ignore[arg-type]
    if entry.type == "self_check":
        return call_self_check(client, cfg, entry)  # type: ignore[arg-type]
    raise ValueError(f"Unknown entry type: {entry.type}")


# ── Orchestration ────────────────────────────────────────────────────────────


def run(
    cfg: RunnerConfig,
    set_path: Path,
    output_dir: Path,
    only_types: set[str] | None = None,
) -> dict:
    entries = load_jsonl(set_path)
    if only_types:
        entries = [e for e in entries if e.type in only_types]
    if not entries:
        raise SystemExit("No entries to run after filtering.")

    output_dir.mkdir(parents=True, exist_ok=True)
    trace_dir = output_dir / "trace"
    trace_dir.mkdir(exist_ok=True)
    responses_path = output_dir / "responses.jsonl"
    meta_path = output_dir / "run_meta.json"

    print(f"[runner] config={cfg.name}  base_url={cfg.base_url}")
    print(f"[runner] set={set_path}  entries={len(entries)}  distribution={summary(entries)}")
    print(f"[runner] output={output_dir}")

    counts = {"ok": 0, "error": 0, "by_type": {}}
    with httpx.Client() as client, open(responses_path, "w", encoding="utf-8") as out:
        for i, entry in enumerate(entries, start=1):
            print(f"  [{i:>3d}/{len(entries)}] {entry.id} ({entry.type}) ... ", end="", flush=True)
            rr, raw = run_entry(client, cfg, entry)
            out.write(json.dumps(rr.to_dict(), ensure_ascii=False) + "\n")
            out.flush()
            if raw is not None:
                with open(trace_dir / f"{entry.id}.json", "w", encoding="utf-8") as tf:
                    json.dump(raw, tf, ensure_ascii=False, indent=2)
            ok = rr.error is None and rr.http_status == 200
            counts["by_type"].setdefault(entry.type, {"ok": 0, "error": 0})
            counts["by_type"][entry.type]["ok" if ok else "error"] += 1
            counts["ok" if ok else "error"] += 1
            print(f"{rr.latency_ms} ms  {'✓' if ok else '✗ ' + (rr.error or 'http ' + str(rr.http_status))[:50]}")
            if cfg.delay_seconds > 0:
                time.sleep(cfg.delay_seconds)

    meta = {
        "config_name": cfg.name,
        "base_url": cfg.base_url,
        "set_path": str(set_path),
        "entry_count": len(entries),
        "distribution": summary(entries),
        "counts": counts,
        "started_at": datetime.utcnow().isoformat() + "Z",
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n[runner] done. ok={counts['ok']} error={counts['error']}")
    print(f"[runner] responses: {responses_path}")
    print(f"[runner] meta: {meta_path}")
    return meta


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="ATLAS eval runner (M3.B)")
    parser.add_argument(
        "--set", type=Path, required=True, help="Путь к golden set JSONL"
    )
    parser.add_argument(
        "--config", type=Path, required=True, help="Путь к runner config (TOML)"
    )
    parser.add_argument(
        "--output", type=Path, help="Output dir (default: eval/results/run-{ts}/)"
    )
    parser.add_argument(
        "--only",
        choices=["qa", "refusal", "formula", "self_check"],
        action="append",
        help="Запустить только entries указанного типа (можно повторять)",
    )
    parser.add_argument(
        "--token-env",
        default="ATLAS_EVAL_TOKEN",
        help="Имя ENV-переменной с JWT токеном",
    )
    args = parser.parse_args()

    if args.output is None:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        args.output = Path("eval/results") / f"run-{ts}"

    cfg = RunnerConfig.load(args.config, token_env=args.token_env)
    run(cfg, args.set, args.output, only_types=set(args.only) if args.only else None)


if __name__ == "__main__":
    main()
