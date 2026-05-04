#!/usr/bin/env python3
"""daily_metrics_report.py — суточная сводка из БД для пилот-чата.

Roadmap §M6.A: «`scripts/daily_metrics_report.py` cron'ом за прошедшие сутки
агрегирует faithfulness (по judged sample), citation accuracy, refusal rate,
error rate, активность пользователей. Шлёт в Telegram-чат разработчика.»

Эта версия покрывает то, что доступно из БД одним запросом без LLM-judge:
активность пользователей, self-check progress, audit-события приватности,
QA-feedback. Поля faithfulness и citation accuracy помечены как TBD —
заполнятся, когда подключится production-judge sample (M6.D).

Запуск:
    python3 scripts/daily_metrics_report.py
    python3 scripts/daily_metrics_report.py --window-hours 24 --tenant optics-kafedra
    python3 scripts/daily_metrics_report.py --json   # машиночитаемый dump в stdout

Cron:
    0 8 * * * cd /home/atlas/atlas && \
        python3 scripts/daily_metrics_report.py >> /home/atlas/reports/daily.log 2>&1

В Telegram бот можно либо парсить stdout, либо `--json` + jq + curl.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def psql_csv(query: str) -> list[list[str]]:
    """Запустить psql внутри docker compose, вернуть CSV-строки без заголовка."""
    proc = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            os.environ.get("POSTGRES_USER", "atlas"),
            "-d",
            os.environ.get("POSTGRES_DB", "atlas"),
            "--csv",
            "--tuples-only",
            "-c",
            query,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    rows = [r for r in proc.stdout.strip().split("\n") if r]
    return [r.split(",") for r in rows]


def scalar(query: str, default: int | float | str = 0) -> str:
    rows = psql_csv(query)
    if not rows:
        return str(default)
    return rows[0][0]


@dataclass
class TenantMetrics:
    tenant_slug: str
    users_total: int
    users_active_24h: int
    users_new_24h: int
    selfcheck_attempts_total: int
    selfcheck_attempts_24h: int
    selfcheck_completed_24h: int
    selfcheck_invalid_24h: int
    qa_feedback_24h: int
    qa_feedback_negative_24h: int
    audit_personal_access_24h: int
    audit_privacy_violation_24h: int
    audit_user_delete_24h: int
    program_topics: int
    materials_active: int
    documents_replaced: int


@dataclass
class Report:
    generated_at: str
    window_hours: int
    placeholder_judge_metrics: dict = field(
        default_factory=lambda: {
            "faithfulness_24h_judged": None,
            "citation_accuracy_24h_judged": None,
            "judge_sample_size": 0,
            "note": "production-judge sampler ещё не подключён (см. M6.D)",
        }
    )
    tenants: list[TenantMetrics] = field(default_factory=list)


def collect(window_hours: int, only_slug: str | None) -> Report:
    where_tenant = f" AND t.slug = '{only_slug}'" if only_slug else ""

    tenant_rows = psql_csv(f"SELECT id, slug FROM tenants WHERE 1=1{where_tenant};")

    report = Report(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        window_hours=window_hours,
    )

    for tid, slug in tenant_rows:
        # users
        users_total = int(scalar(
            f"SELECT count(*) FROM users WHERE tenant_id = '{tid}' AND deleted_at IS NULL;"
        ))
        users_new_24h = int(scalar(
            f"SELECT count(*) FROM users WHERE tenant_id = '{tid}' "
            f"AND deleted_at IS NULL "
            f"AND created_at > now() - interval '{window_hours} hours';"
        ))
        users_active_24h = int(scalar(
            f"SELECT count(DISTINCT user_id) FROM ("
            f"  SELECT user_id FROM sessions WHERE tenant_id = '{tid}' "
            f"    AND updated_at > now() - interval '{window_hours} hours' "
            f"  UNION ALL "
            f"  SELECT user_id FROM selfcheck_attempts WHERE tenant_id = '{tid}' "
            f"    AND created_at > now() - interval '{window_hours} hours' "
            f"    AND user_id IS NOT NULL"
            f") s;"
        ))

        # self-check
        sc_total = int(scalar(
            f"SELECT count(*) FROM selfcheck_attempts WHERE tenant_id = '{tid}';"
        ))
        sc_24 = int(scalar(
            f"SELECT count(*) FROM selfcheck_attempts WHERE tenant_id = '{tid}' "
            f"AND created_at > now() - interval '{window_hours} hours';"
        ))
        sc_completed_24 = int(scalar(
            f"SELECT count(*) FROM selfcheck_attempts WHERE tenant_id = '{tid}' "
            f"AND status = 'completed' "
            f"AND completed_at > now() - interval '{window_hours} hours';"
        ))
        sc_invalid_24 = int(scalar(
            f"SELECT count(*) FROM selfcheck_attempts WHERE tenant_id = '{tid}' "
            f"AND status = 'invalid_evaluation' "
            f"AND created_at > now() - interval '{window_hours} hours';"
        ))

        # qa_feedback
        fb_24 = int(scalar(
            f"SELECT count(*) FROM qa_feedback WHERE tenant_id = '{tid}' "
            f"AND created_at > now() - interval '{window_hours} hours';"
        ))
        fb_neg_24 = int(scalar(
            f"SELECT count(*) FROM qa_feedback WHERE tenant_id = '{tid}' "
            f"AND created_at > now() - interval '{window_hours} hours' "
            f"AND rating IN ('negative','incorrect');"
        ))

        # audit privacy
        audit_pa_24 = int(scalar(
            f"SELECT count(*) FROM audit_log WHERE tenant_id = '{tid}' "
            f"AND action = 'personal_data.access' "
            f"AND occurred_at > now() - interval '{window_hours} hours';"
        ))
        audit_pv_24 = int(scalar(
            f"SELECT count(*) FROM audit_log WHERE tenant_id = '{tid}' "
            f"AND action LIKE 'privacy.violation_attempt%' "
            f"AND occurred_at > now() - interval '{window_hours} hours';"
        ))
        audit_ud_24 = int(scalar(
            f"SELECT count(*) FROM audit_log WHERE tenant_id = '{tid}' "
            f"AND action = 'user.delete' "
            f"AND occurred_at > now() - interval '{window_hours} hours';"
        ))

        # corpus state
        topics = int(scalar(
            f"SELECT count(*) FROM program_topics pt "
            f"JOIN programs p ON p.id = pt.program_id WHERE p.tenant_id = '{tid}';"
        ))
        materials = int(scalar(
            f"SELECT count(*) FROM documents WHERE tenant_id = '{tid}' AND status = 'active';"
        ))
        replaced = int(scalar(
            f"SELECT count(*) FROM documents WHERE tenant_id = '{tid}' AND status = 'replaced';"
        ))

        report.tenants.append(TenantMetrics(
            tenant_slug=slug,
            users_total=users_total,
            users_active_24h=users_active_24h,
            users_new_24h=users_new_24h,
            selfcheck_attempts_total=sc_total,
            selfcheck_attempts_24h=sc_24,
            selfcheck_completed_24h=sc_completed_24,
            selfcheck_invalid_24h=sc_invalid_24,
            qa_feedback_24h=fb_24,
            qa_feedback_negative_24h=fb_neg_24,
            audit_personal_access_24h=audit_pa_24,
            audit_privacy_violation_24h=audit_pv_24,
            audit_user_delete_24h=audit_ud_24,
            program_topics=topics,
            materials_active=materials,
            documents_replaced=replaced,
        ))

    return report


def render_markdown(report: Report) -> str:
    lines: list[str] = []
    lines.append(f"# ATLAS daily metrics — {report.generated_at}")
    lines.append(f"_Window: last {report.window_hours}h_")
    lines.append("")

    if not report.tenants:
        lines.append("**Нет тенантов в БД.**")
        return "\n".join(lines)

    for tm in report.tenants:
        lines.append(f"## tenant: `{tm.tenant_slug}`")
        lines.append("")
        lines.append("**Users**")
        lines.append(
            f"- total active accounts: **{tm.users_total}** "
            f"(+{tm.users_new_24h} new in window)"
        )
        lines.append(
            f"- active in window: **{tm.users_active_24h}** "
            f"(хотя бы один session/selfcheck)"
        )
        lines.append("")
        lines.append("**Self-check**")
        lines.append(
            f"- attempts всего: {tm.selfcheck_attempts_total} "
            f"(+{tm.selfcheck_attempts_24h} в окне)"
        )
        lines.append(
            f"- completed в окне: {tm.selfcheck_completed_24h}, "
            f"invalid_evaluation: {tm.selfcheck_invalid_24h}"
        )
        lines.append("")
        lines.append("**Q&A feedback**")
        lines.append(
            f"- получено в окне: {tm.qa_feedback_24h} "
            f"(из них negative/incorrect: {tm.qa_feedback_negative_24h})"
        )
        if tm.qa_feedback_24h:
            neg_pct = round(100 * tm.qa_feedback_negative_24h / tm.qa_feedback_24h, 1)
            lines.append(f"- negative-rate: {neg_pct}%")
        lines.append("")
        lines.append("**Privacy / governance (audit_log)**")
        lines.append(
            f"- personal_data.access: {tm.audit_personal_access_24h}, "
            f"privacy.violation_attempt: {tm.audit_privacy_violation_24h}, "
            f"user.delete: {tm.audit_user_delete_24h}"
        )
        if tm.audit_privacy_violation_24h:
            lines.append("  ⚠️ **есть попытки нарушения** — проверь incident-runbook §1")
        lines.append("")
        lines.append("**Корпус**")
        lines.append(
            f"- topics в программе: {tm.program_topics}, "
            f"active materials: {tm.materials_active}, "
            f"replaced: {tm.documents_replaced}"
        )
        lines.append("")

    pj = report.placeholder_judge_metrics
    lines.append("## Качество (production-judge sample)")
    lines.append(f"- faithfulness 24h: `{pj['faithfulness_24h_judged']}`")
    lines.append(f"- citation accuracy 24h: `{pj['citation_accuracy_24h_judged']}`")
    lines.append(f"- judge sample size: {pj['judge_sample_size']}")
    lines.append(f"- note: {pj['note']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--tenant", default=None, help="ограничить одним tenant slug")
    parser.add_argument(
        "--json",
        action="store_true",
        help="вывести JSON вместо markdown (для машинного парсинга)",
    )
    args = parser.parse_args(argv)

    try:
        report = collect(args.window_hours, args.tenant)
    except subprocess.CalledProcessError as exc:
        print(f"[daily_metrics] psql call failed: {exc.stderr}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "generated_at": report.generated_at,
                    "window_hours": report.window_hours,
                    "judge_metrics": report.placeholder_judge_metrics,
                    "tenants": [tm.__dict__ for tm in report.tenants],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
