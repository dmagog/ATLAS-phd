"""Eval dashboard data API (Phase 5.2).

Reads eval-runner outputs from /app/eval/results/* (mounted read-only)
and aggregates them for the /eval HTML dashboard.

Exposes:
  * GET /eval/dashboard — full data for the dashboard view (super-admin only).

Source files in each run directory:
  * summary.json         — aggregate metrics (always present)
  * run_meta.json        — config + counts + started_at
  * responses.jsonl      — per-entry response records (for per-topic breakdown)
  * faithfulness_detail.json — per-entry faithfulness scores (optional)
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import require_super_admin
from atlas.db.models import Program, ProgramTopic, Tenant, User
from atlas.db.session import get_db

router = APIRouter(prefix="/eval", tags=["eval"])

EVAL_RESULTS_DIR = Path("/app/eval/results")
EVAL_GOLDEN_SET = Path("/app/eval/golden_set_v1/golden_set_v1.0.jsonl")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _scan_runs() -> list[dict]:
    """Return list of completed runs, newest first.

    Each entry: {dir, config_name, started_at, summary, meta}.
    Skips dirs without summary.json or with malformed JSON.
    """
    if not EVAL_RESULTS_DIR.exists():
        return []
    runs = []
    for d in EVAL_RESULTS_DIR.iterdir():
        if not d.is_dir():
            continue
        summary_p = d / "summary.json"
        meta_p = d / "run_meta.json"
        if not summary_p.exists():
            continue
        try:
            summary = json.loads(summary_p.read_text())
            meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
        except (json.JSONDecodeError, OSError):
            continue
        runs.append({
            "dir_name": d.name,
            "config_name": meta.get("config_name") or summary.get("config_name") or "unknown",
            "started_at": meta.get("started_at") or "",
            "summary": summary,
            "meta": meta,
        })
    # Sort by started_at desc; fall back to dir name (which embeds timestamp).
    runs.sort(key=lambda r: (r["started_at"] or r["dir_name"]), reverse=True)
    return runs


def _per_topic_breakdown(run_dir: Path, topic_titles: dict[str, str]) -> list[dict]:
    """Replicate eval/per_topic_breakdown.py logic — per-topic aggregates.

    Returns list of {id, title, total, answered, refused, faith_n, faith_mu,
    sc_n, sc_mae} sorted by topic id.
    """
    responses_p = run_dir / "responses.jsonl"
    if not responses_p.exists() or not EVAL_GOLDEN_SET.exists():
        return []

    entries = {}
    for line in EVAL_GOLDEN_SET.open():
        e = json.loads(line)
        entries[e["id"]] = e

    faith_path = run_dir / "faithfulness_detail.json"
    faith_by_id: dict[str, float] = {}
    if faith_path.exists():
        for rec in json.load(faith_path.open()):
            if rec.get("score") is not None and not rec.get("error"):
                faith_by_id[rec["entry_id"]] = float(rec["score"])

    by_topic: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "answered": 0, "refused": 0, "error": 0,
        "faith_scores": [], "sc_diffs": [],
    })

    for line in responses_p.open():
        r = json.loads(line)
        eid = r["entry_id"]
        e = entries.get(eid)
        if not e:
            continue
        tid = e.get("topic_external_id")
        if not tid:
            continue  # refusal entries have no topic

        b = by_topic[tid]
        b["total"] += 1
        st = r.get("api_status")
        if st == "answered":
            b["answered"] += 1
        elif st in ("refused", "refusal"):
            b["refused"] += 1
        else:
            b["error"] += 1

        if eid in faith_by_id:
            b["faith_scores"].append(faith_by_id[eid])
        if e.get("type") == "self_check" and r.get("sc_overall_score") is not None:
            try:
                diff = abs(float(e["expected_overall"]) - float(r["sc_overall_score"]))
                b["sc_diffs"].append(diff)
            except (KeyError, ValueError, TypeError):
                pass

    out = []
    for tid in sorted(by_topic):
        b = by_topic[tid]
        out.append({
            "id": tid,
            "title": topic_titles.get(tid, tid),
            "total": b["total"],
            "answered": b["answered"],
            "refused": b["refused"],
            "error": b["error"],
            "faith_n": len(b["faith_scores"]),
            "faith_mu": statistics.mean(b["faith_scores"]) if b["faith_scores"] else None,
            "sc_n": len(b["sc_diffs"]),
            "sc_mae": statistics.mean(b["sc_diffs"]) if b["sc_diffs"] else None,
        })
    return out


def _reproducibility_stats(treatment_runs: list[dict]) -> dict | None:
    """For up to N most recent treatment runs, compute spread of key metrics."""
    if len(treatment_runs) < 2:
        return None
    sample = treatment_runs[:7]
    refusal_tnrs = []
    kappas = []
    p95s = []
    for r in sample:
        m = r["summary"].get("metrics") or {}
        rc = m.get("refusal_correctness") or {}
        v = rc.get("refusal_tnr")
        if v is not None:
            refusal_tnrs.append(v)
        sc = m.get("selfcheck_rubric") or {}
        v = sc.get("kappa_binarized")
        if v is not None:
            kappas.append(v)
        lat = m.get("latency") or {}
        v = lat.get("p95_ms")
        if v is not None:
            p95s.append(v)

    def stats(xs: list[float]) -> dict | None:
        if not xs:
            return None
        return {
            "n": len(xs),
            "mean": statistics.mean(xs),
            "stdev": statistics.stdev(xs) if len(xs) > 1 else 0.0,
            "min": min(xs),
            "max": max(xs),
        }

    return {
        "n_runs": len(sample),
        "refusal_tnr": stats(refusal_tnrs),
        "kappa_binarized": stats(kappas),
        "latency_p95_ms": stats(p95s),
    }


async def _topic_titles_for_pilot(db: AsyncSession) -> dict[str, str]:
    """Map external_id → title from the pilot tenant's active program.

    No SQLAlchemy relationship is declared between Program and ProgramTopic,
    so we join via raw FK columns.
    """
    pilot = (
        await db.execute(select(Tenant).where(Tenant.slug == "optics-kafedra"))
    ).scalar_one_or_none()
    if not pilot:
        return {}
    rows = (
        await db.execute(
            select(ProgramTopic.external_id, ProgramTopic.title)
            .join(Program, Program.id == ProgramTopic.program_id)
            .where(Program.tenant_id == pilot.id)
        )
    ).all()
    return {r[0]: r[1] for r in rows}


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------
class RunInfo(BaseModel):
    dir_name: str
    config_name: str
    started_at: str
    refusal_tnr: float | None
    kappa_binarized: float | None


class TopicRow(BaseModel):
    id: str
    title: str
    total: int
    answered: int
    refused: int
    error: int
    faith_n: int
    faith_mu: float | None
    sc_n: int
    sc_mae: float | None


class DashboardOut(BaseModel):
    has_data: bool
    latest_treatment: dict | None
    latest_baseline: dict | None
    per_topic: list[TopicRow]
    reproducibility: dict | None
    history: list[RunInfo]


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
) -> DashboardOut:
    runs = _scan_runs()
    if not runs:
        return DashboardOut(
            has_data=False,
            latest_treatment=None,
            latest_baseline=None,
            per_topic=[],
            reproducibility=None,
            history=[],
        )

    latest_treatment = next((r for r in runs if r["config_name"] == "treatment"), None)
    latest_baseline = next((r for r in runs if r["config_name"] == "baseline"), None)

    per_topic: list[TopicRow] = []
    if latest_treatment:
        topic_titles = await _topic_titles_for_pilot(db)
        rows = _per_topic_breakdown(EVAL_RESULTS_DIR / latest_treatment["dir_name"], topic_titles)
        per_topic = [TopicRow(**r) for r in rows]

    reproducibility = _reproducibility_stats([r for r in runs if r["config_name"] == "treatment"])

    history: list[RunInfo] = []
    for r in runs[:12]:
        m = r["summary"].get("metrics") or {}
        rc = m.get("refusal_correctness") or {}
        sc = m.get("selfcheck_rubric") or {}
        history.append(RunInfo(
            dir_name=r["dir_name"],
            config_name=r["config_name"],
            started_at=r["started_at"],
            refusal_tnr=rc.get("refusal_tnr"),
            kappa_binarized=sc.get("kappa_binarized"),
        ))

    def _pack(r: dict | None) -> dict | None:
        if not r:
            return None
        return {
            "dir_name": r["dir_name"],
            "config_name": r["config_name"],
            "started_at": r["started_at"],
            "summary": r["summary"],
            "meta": r["meta"],
        }

    return DashboardOut(
        has_data=True,
        latest_treatment=_pack(latest_treatment),
        latest_baseline=_pack(latest_baseline),
        per_topic=per_topic,
        reproducibility=reproducibility,
        history=history,
    )
