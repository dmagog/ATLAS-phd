"""Supervisor analytics (M5.B + M5.D, BDD 5.1, 5.2, 5.3, 5.4, 5.5, 5.7).

Endpoints scoped to a single tenant; supervisor sees only their own
tenant; super-admin can pin any tenant via X-Atlas-Tenant header (M4.C
override). Tenant-admin also gets read access — they need the same
"where are gaps" view to triage corpus coverage.

  GET /tenants/{slug}/supervisor/heatmap
      — per-topic aggregation with fail_rate + Wilson 95% CI.
        N-threshold: returns empty list if tenant has < min_aggregate_size
        active students or < min_attempts_for_heatmap completed attempts
        (BDD 5.3 + 5.6 first-time onboarding signal).

  GET /tenants/{slug}/supervisor/topics/{topic_id}/drilldown
      — per-topic breakdown: top error_tags, attempt counts.

  GET /tenants/{slug}/supervisor/students
      — list of students; PII visible only when student opted in
        (supervisor_visibility='show-to-supervisor'). Otherwise the
        row appears as 'Аспирант #N'.

  GET /tenants/{slug}/supervisor/students/{student_id}/profile
      — full per-student profile. Hard-fails 404 (not 403, BDD 5.5
        anti-leak) when student didn't opt in or doesn't exist; logs
        'privacy.violation_attempt' otherwise.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import get_current_user
from atlas.db.audit import write_audit
from atlas.db.models import (
    Program,
    ProgramTopic,
    SelfCheckAttempt,
    Tenant,
    User,
    UserRole,
)
from atlas.db.session import get_db

router = APIRouter(prefix="/tenants", tags=["supervisor"])


# Supervisor analytics access set: supervisor + tenant-admin + super-admin.
_SUPERVISOR_ROLES = {
    UserRole.supervisor.value,
    UserRole.tenant_admin.value,
    UserRole.super_admin.value,
}


async def _resolve_tenant_for_supervisor(
    slug: str, user: User, db: AsyncSession
) -> Tenant:
    """Resolve tenant slug + check the user is allowed to read its analytics."""
    if user.role not in _SUPERVISOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: requires supervisor / tenant-admin / super-admin",
        )
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant not found: {slug}"
        )
    if user.role != UserRole.super_admin.value and user.tenant_id != tenant.id:
        # Bound supervisor/tenant-admin can only see their own tenant.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant analytics forbidden",
        )
    return tenant


# ─── M5.B: heatmap ──────────────────────────────────────────────────────


def _wilson_interval(below: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95%-CI Wilson interval for a proportion (below/total).
    Computed in app code per M3.B/M5 design (PostgreSQL has no native).
    """
    if total <= 0:
        return 0.0, 0.0
    p = below / total
    denom = 1.0 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1.0 - p) / total + z * z / (4 * total * total)) / denom
    lo = max(0.0, centre - half)
    hi = min(1.0, centre + half)
    return round(lo, 4), round(hi, 4)


# Defaults from roadmap §M5.B (BDD 5.3, 5.6).
_MIN_AGG_SIZE_DEFAULT = 5
_MIN_ATTEMPTS_HEATMAP_DEFAULT = 30


class HeatmapTopicRow(BaseModel):
    topic_id: str
    external_id: str
    section: str
    title: str
    total_attempts: int
    distinct_students: int
    below_threshold: int
    fail_rate: float
    ci_low: float
    ci_high: float


class HeatmapOut(BaseModel):
    program_version: str | None
    threshold_score: float  # what counts as "failed": score < this
    n_students_active: int
    n_attempts_completed: int
    is_below_threshold: bool  # True → heatmap is empty for privacy
    threshold_reason: str | None  # "n_students" | "n_attempts" | None
    topics: list[HeatmapTopicRow]


@router.get("/{slug}/supervisor/heatmap", response_model=HeatmapOut)
async def supervisor_heatmap(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HeatmapOut:
    tenant = await _resolve_tenant_for_supervisor(slug, current_user, db)

    cfg = (tenant.config or {}).get("analytics") or {}
    min_n_students = int(cfg.get("min_aggregate_size", _MIN_AGG_SIZE_DEFAULT))
    min_n_attempts = int(cfg.get("min_attempts_for_heatmap", _MIN_ATTEMPTS_HEATMAP_DEFAULT))
    threshold_score = float(cfg.get("score_threshold", 3.0))

    # Population gates (BDD 5.3).
    n_students_row = await db.execute(
        sql_text(
            "SELECT COUNT(*) FROM users "
            "WHERE tenant_id = :tid AND role = 'student' AND deleted_at IS NULL"
        ),
        {"tid": tenant.id},
    )
    n_students_active = int(n_students_row.scalar() or 0)

    n_attempts_row = await db.execute(
        sql_text(
            "SELECT COUNT(*) FROM selfcheck_attempts "
            "WHERE tenant_id = :tid AND status = 'completed'"
        ),
        {"tid": tenant.id},
    )
    n_attempts_completed = int(n_attempts_row.scalar() or 0)

    # Active program lookup (for program_version display).
    prog_result = await db.execute(
        select(Program).where(Program.tenant_id == tenant.id, Program.status == "active")
    )
    program = prog_result.scalar_one_or_none()

    is_below = False
    threshold_reason: str | None = None
    if n_students_active < min_n_students:
        is_below = True
        threshold_reason = "n_students"
    elif n_attempts_completed < min_n_attempts:
        is_below = True
        threshold_reason = "n_attempts"

    if is_below or program is None:
        return HeatmapOut(
            program_version=program.version if program else None,
            threshold_score=threshold_score,
            n_students_active=n_students_active,
            n_attempts_completed=n_attempts_completed,
            is_below_threshold=is_below or program is None,
            threshold_reason=threshold_reason or ("no_program" if program is None else None),
            topics=[],
        )

    # Aggregate per-topic (only the active program's topics).
    rows = await db.execute(
        sql_text(
            """
            SELECT
                pt.id AS topic_id,
                pt.external_id,
                pt.section,
                pt.title,
                pt.ordinal,
                COUNT(sa.id)                                                  AS total,
                COUNT(DISTINCT sa.user_id)                                    AS distinct_students,
                COUNT(*) FILTER (
                    WHERE (sa.evaluation->>'overall_score')::numeric < :thr
                )                                                             AS below
            FROM program_topics pt
            LEFT JOIN selfcheck_attempts sa
                ON sa.topic_id = pt.id
               AND sa.tenant_id = :tid
               AND sa.status = 'completed'
            WHERE pt.program_id = :pid
            GROUP BY pt.id, pt.external_id, pt.section, pt.title, pt.ordinal
            ORDER BY
                CASE WHEN COUNT(sa.id) = 0 THEN 1 ELSE 0 END,
                COUNT(*) FILTER (
                    WHERE (sa.evaluation->>'overall_score')::numeric < :thr
                )::numeric / NULLIF(COUNT(sa.id), 0) DESC NULLS LAST,
                pt.ordinal ASC
            """
        ),
        {"tid": tenant.id, "pid": program.id, "thr": threshold_score},
    )

    topics: list[HeatmapTopicRow] = []
    for row in rows.mappings():
        total = int(row["total"] or 0)
        below = int(row["below"] or 0)
        fail_rate = below / total if total > 0 else 0.0
        ci_low, ci_high = _wilson_interval(below, total)
        topics.append(
            HeatmapTopicRow(
                topic_id=str(row["topic_id"]),
                external_id=row["external_id"],
                section=row["section"],
                title=row["title"],
                total_attempts=total,
                distinct_students=int(row["distinct_students"] or 0),
                below_threshold=below,
                fail_rate=round(fail_rate, 4),
                ci_low=ci_low,
                ci_high=ci_high,
            )
        )

    return HeatmapOut(
        program_version=program.version,
        threshold_score=threshold_score,
        n_students_active=n_students_active,
        n_attempts_completed=n_attempts_completed,
        is_below_threshold=False,
        threshold_reason=None,
        topics=topics,
    )


# ─── M5.B: drilldown ────────────────────────────────────────────────────


class DrilldownTagRow(BaseModel):
    error_tag: str
    occurrences: int


class DrilldownOut(BaseModel):
    topic_id: str
    external_id: str
    title: str
    total_attempts: int
    below_threshold: int
    error_tags: list[DrilldownTagRow]


@router.get(
    "/{slug}/supervisor/topics/{topic_id}/drilldown",
    response_model=DrilldownOut,
)
async def supervisor_drilldown(
    slug: str,
    topic_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DrilldownOut:
    tenant = await _resolve_tenant_for_supervisor(slug, current_user, db)
    try:
        topic_uuid = uuid.UUID(topic_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid topic_id: {topic_id}",
        )

    # Topic must be in this tenant's active program.
    topic_row = await db.execute(
        sql_text(
            """
            SELECT pt.id, pt.external_id, pt.title
            FROM program_topics pt
            JOIN programs p ON p.id = pt.program_id
            WHERE pt.id = :tpid AND p.tenant_id = :tid AND p.status = 'active'
            """
        ),
        {"tpid": topic_uuid, "tid": tenant.id},
    )
    topic_data = topic_row.mappings().first()
    if topic_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found in active program",
        )

    cfg = (tenant.config or {}).get("analytics") or {}
    threshold_score = float(cfg.get("score_threshold", 3.0))

    counts = await db.execute(
        sql_text(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE (evaluation->>'overall_score')::numeric < :thr) AS below
            FROM selfcheck_attempts
            WHERE topic_id = :tpid AND tenant_id = :tid AND status = 'completed'
            """
        ),
        {"tpid": topic_uuid, "tid": tenant.id, "thr": threshold_score},
    )
    cnt = counts.mappings().first()
    total = int(cnt["total"] or 0)
    below = int(cnt["below"] or 0)

    # Aggregate error tags from below-threshold attempts.
    tag_rows = await db.execute(
        sql_text(
            """
            SELECT tag, COUNT(*) AS occurrences
            FROM (
                SELECT jsonb_array_elements_text(
                           (evaluation::jsonb)->'error_tags'
                       ) AS tag
                FROM selfcheck_attempts
                WHERE topic_id = :tpid
                  AND tenant_id = :tid
                  AND status = 'completed'
                  AND (evaluation->>'overall_score')::numeric < :thr
            ) sub
            GROUP BY tag
            ORDER BY occurrences DESC
            """
        ),
        {"tpid": topic_uuid, "tid": tenant.id, "thr": threshold_score},
    )

    return DrilldownOut(
        topic_id=str(topic_data["id"]),
        external_id=topic_data["external_id"],
        title=topic_data["title"],
        total_attempts=total,
        below_threshold=below,
        error_tags=[
            DrilldownTagRow(
                error_tag=str(r["tag"]),
                occurrences=int(r["occurrences"]),
            )
            for r in tag_rows.mappings()
        ],
    )


# ─── M5.D: students list (with privacy mask) ────────────────────────────


class StudentRow(BaseModel):
    student_id: str | None  # null when anonymized
    display_name: str
    visible: bool  # True iff opted in
    last_attempt_at: datetime | None
    total_attempts: int


class StudentsListOut(BaseModel):
    n_total: int
    n_visible: int  # how many opted in
    students: list[StudentRow]


@router.get("/{slug}/supervisor/students", response_model=StudentsListOut)
async def supervisor_students_list(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StudentsListOut:
    """List students in the tenant with privacy mask (BDD 5.7).

    Opted-in students appear with their email and student_id (so
    supervisor can drill into a profile). Others are anonymized
    `Аспирант #N` and the supervisor cannot follow up on them
    individually.
    """
    tenant = await _resolve_tenant_for_supervisor(slug, current_user, db)

    rows = await db.execute(
        sql_text(
            """
            SELECT
                u.id,
                u.email,
                u.supervisor_visibility,
                COALESCE(stats.total, 0) AS total_attempts,
                stats.last_at
            FROM users u
            LEFT JOIN (
                SELECT user_id, COUNT(*) AS total, MAX(completed_at) AS last_at
                FROM selfcheck_attempts
                WHERE tenant_id = :tid AND status = 'completed' AND user_id IS NOT NULL
                GROUP BY user_id
            ) stats ON stats.user_id = u.id
            WHERE u.tenant_id = :tid
              AND u.role = 'student'
              AND u.deleted_at IS NULL
            ORDER BY u.created_at
            """
        ),
        {"tid": tenant.id},
    )

    students: list[StudentRow] = []
    n_visible = 0
    for idx, r in enumerate(rows.mappings(), start=1):
        opted_in = r["supervisor_visibility"] == "show-to-supervisor"
        if opted_in:
            n_visible += 1
            students.append(
                StudentRow(
                    student_id=str(r["id"]),
                    display_name=r["email"],
                    visible=True,
                    last_attempt_at=r["last_at"],
                    total_attempts=int(r["total_attempts"] or 0),
                )
            )
        else:
            students.append(
                StudentRow(
                    student_id=None,
                    display_name=f"Аспирант #{idx}",
                    visible=False,
                    last_attempt_at=r["last_at"],
                    total_attempts=int(r["total_attempts"] or 0),
                )
            )

    return StudentsListOut(
        n_total=len(students), n_visible=n_visible, students=students
    )


# ─── M5.D + M5.C: student profile (consent gate) ────────────────────────


class StudentProfileTopicRow(BaseModel):
    external_id: str
    title: str
    total_attempts: int
    last_score: float | None
    last_at: datetime | None


class StudentProfileOut(BaseModel):
    student_id: str
    email: str
    total_attempts: int
    last_attempt_at: datetime | None
    topics: list[StudentProfileTopicRow]


@router.get(
    "/{slug}/supervisor/students/{student_id}/profile",
    response_model=StudentProfileOut,
)
async def supervisor_student_profile(
    slug: str,
    student_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StudentProfileOut:
    """BDD 5.4 + 5.5: per-student profile only when opted in.

    Privacy posture (BDD 5.5): when the student exists but didn't opt in
    (or doesn't exist at all in this tenant), respond 404. Do NOT
    distinguish — that would leak existence. Audit-log the attempt as
    'privacy.violation_attempt' in the not-opted-in case (we still know
    privately the user does exist).
    """
    tenant = await _resolve_tenant_for_supervisor(slug, current_user, db)
    try:
        student_uuid = uuid.UUID(student_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid student_id: {student_id}",
        )

    user_row = await db.execute(
        select(User).where(
            User.id == student_uuid,
            User.tenant_id == tenant.id,
            User.role == UserRole.student.value,
            User.deleted_at.is_(None),
        )
    )
    student = user_row.scalar_one_or_none()

    if student is None:
        # Doesn't exist (or deleted) — plain 404, no audit (no privacy
        # event because there's nothing to leak).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )

    if student.supervisor_visibility != "show-to-supervisor":
        # Exists but not opted in: log violation_attempt, return 404 (no leak).
        await write_audit(
            db,
            action="privacy.violation_attempt",
            actor_id=current_user.id,
            actor_role=current_user.role,
            tenant_id=tenant.id,
            target_type="user",
            target_id=str(student.id),
            request_id=str(request.headers.get("x-request-id", "")),
            details={"reason": "student_not_opted_in"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )

    # Opted in → audit personal_data.access and return profile.
    await write_audit(
        db,
        action="personal_data.access",
        actor_id=current_user.id,
        actor_role=current_user.role,
        tenant_id=tenant.id,
        target_type="user",
        target_id=str(student.id),
        details={"surface": "supervisor.student_profile"},
        flush_only=True,
    )

    # Topic-level summary.
    topic_rows = await db.execute(
        sql_text(
            """
            WITH last_per_topic AS (
                SELECT DISTINCT ON (sa.topic_id)
                    sa.topic_id,
                    (sa.evaluation->>'overall_score')::numeric AS score,
                    sa.completed_at
                FROM selfcheck_attempts sa
                WHERE sa.user_id = :uid
                  AND sa.tenant_id = :tid
                  AND sa.status = 'completed'
                  AND sa.topic_id IS NOT NULL
                ORDER BY sa.topic_id, sa.completed_at DESC
            ),
            counts_per_topic AS (
                SELECT topic_id, COUNT(*) AS total
                FROM selfcheck_attempts
                WHERE user_id = :uid AND tenant_id = :tid AND status = 'completed'
                  AND topic_id IS NOT NULL
                GROUP BY topic_id
            )
            SELECT
                pt.id AS topic_id,
                pt.external_id,
                pt.title,
                pt.ordinal,
                COALESCE(c.total, 0) AS total,
                lpt.score AS last_score,
                lpt.completed_at AS last_at
            FROM program_topics pt
            LEFT JOIN last_per_topic lpt ON lpt.topic_id = pt.id
            LEFT JOIN counts_per_topic c ON c.topic_id = pt.id
            JOIN programs p ON p.id = pt.program_id AND p.status = 'active'
            WHERE p.tenant_id = :tid
              AND COALESCE(c.total, 0) > 0
            ORDER BY pt.ordinal
            """
        ),
        {"uid": student.id, "tid": tenant.id},
    )

    total_overall_row = await db.execute(
        sql_text(
            "SELECT COUNT(*) AS n, MAX(completed_at) AS last_at "
            "FROM selfcheck_attempts WHERE user_id = :uid AND tenant_id = :tid "
            "AND status = 'completed'"
        ),
        {"uid": student.id, "tid": tenant.id},
    )
    overall = total_overall_row.mappings().first()

    await db.commit()

    return StudentProfileOut(
        student_id=str(student.id),
        email=student.email,
        total_attempts=int(overall["n"] or 0),
        last_attempt_at=overall["last_at"],
        topics=[
            StudentProfileTopicRow(
                external_id=r["external_id"],
                title=r["title"],
                total_attempts=int(r["total"]),
                last_score=(float(r["last_score"]) if r["last_score"] is not None else None),
                last_at=r["last_at"],
            )
            for r in topic_rows.mappings()
        ],
    )
