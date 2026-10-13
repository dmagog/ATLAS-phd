"""User self-management ('me' endpoints, M5.A).

Currently scoped to:
  * GET  /me — basic profile + visibility flag.
  * GET  /me/program — topics of the active program in the caller's tenant
    context (any role; super-admin picks the tenant via X-Atlas-Tenant).
  * GET  /me/visibility — current supervisor_visibility setting.
  * POST /me/visibility — student/supervisor/tenant-admin toggles their
    own opt-in for supervisor analytics (BDD 3.4). The change is logged
    in audit_log so any supervisor access during a covered period can
    be reconstructed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.config import settings
from atlas.core.deps import get_current_user
from atlas.db.audit import write_audit
from atlas.db.models import Program, ProgramTopic, SupervisorVisibility, Tenant, User
from atlas.db.session import get_db

router = APIRouter(prefix="/me", tags=["me"])


class MeOut(BaseModel):
    id: str
    email: str
    role: str
    tenant_id: str | None
    tenant_slug: str | None
    tenant_display_name: str | None
    supervisor_visibility: str
    visibility_changed_at: datetime | None
    # super-admin: тенант, в котором бэкенд работает без X-Atlas-Tenant.
    default_tenant_slug: str | None = None


class StudyTopicOut(BaseModel):
    external_id: str
    section: str
    title: str
    coverage_chunks: int
    # Готовый вопрос для подсказки в чате (см. _study_prompt).
    prompt: str


_PROMPT_CONCEPTS = 4


def _study_prompt(title: str, section: str, key_concepts: list[str]) -> str:
    """Вопрос «по теме» для чата.

    Формулировка выбрана замером retrieval на программе IPMA (28 тем):
    «Что важно знать по теме «T»: k1, k2, k3, k4» проходит hard-gate на
    28/28 и приводит к собственному разделу темы в источнике, тогда как
    «Расскажи о теме: T (раздел)» — 26/28 и чаще цепляет оглавление.
    Ключевые понятия с тем же началом, что у уже взятых, пропускаются —
    в программе бывают варианты одного слова для автопривязки материалов.
    С названием темы не сравниваем: «дифракционная решётка» в теме
    «Дифракция…» нужна retrieval'у (без неё тема оптики не проходит gate).
    """
    picked: list[str] = []
    seen: set[str] = set()
    for kc in key_concepts:
        head = kc.lower()[:5]
        if head in seen:
            continue
        seen.add(head)
        picked.append(kc)
        if len(picked) == _PROMPT_CONCEPTS:
            break
    if not picked:
        return f"Расскажи о теме: {title} ({section})"
    return f"Что важно знать по теме «{title}»: {', '.join(picked)}"


class StudyProgramOut(BaseModel):
    tenant_slug: str
    version: str | None
    topics: list[StudyTopicOut]


class VisibilityOut(BaseModel):
    supervisor_visibility: str
    visibility_changed_at: datetime | None


class SetVisibilityRequest(BaseModel):
    visibility: Literal["anonymous-aggregate-only", "show-to-supervisor"]


@router.get("", response_model=MeOut)
async def me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeOut:
    tenant_slug = None
    tenant_display_name = None
    if current_user.tenant_id is not None:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
        ).scalar_one_or_none()
        if tenant is not None:
            tenant_slug = tenant.slug
            tenant_display_name = tenant.display_name
    return MeOut(
        id=str(current_user.id),
        email=current_user.email,
        role=current_user.role,
        tenant_id=str(current_user.tenant_id) if current_user.tenant_id else None,
        tenant_slug=tenant_slug,
        tenant_display_name=tenant_display_name,
        supervisor_visibility=current_user.supervisor_visibility,
        visibility_changed_at=current_user.visibility_changed_at,
        default_tenant_slug=(
            settings.pilot_tenant_slug if current_user.tenant_id is None else None
        ),
    )


@router.get("/program", response_model=StudyProgramOut)
async def my_program(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StudyProgramOut:
    """Темы активной программы — для выбора темы в чате и самопроверке.

    Read-only и без key_concepts: студенту нужен только список билетов.
    Полная программа (с key_concepts) — GET /tenants/{slug}/program,
    только для tenant-admin.
    """
    from atlas.db.tenant_helpers import resolve_tenant_id_for_user

    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
    program = (
        await db.execute(
            select(Program).where(Program.tenant_id == tenant_id, Program.status == "active")
        )
    ).scalar_one_or_none()
    if program is None:
        return StudyProgramOut(tenant_slug=tenant.slug, version=None, topics=[])
    topics = (
        await db.execute(
            select(ProgramTopic)
            .where(ProgramTopic.program_id == program.id)
            .order_by(ProgramTopic.ordinal)
        )
    ).scalars().all()
    return StudyProgramOut(
        tenant_slug=tenant.slug,
        version=program.version,
        topics=[
            StudyTopicOut(
                external_id=t.external_id,
                section=t.section,
                title=t.title,
                coverage_chunks=t.coverage_chunks,
                prompt=_study_prompt(t.title, t.section, t.key_concepts or []),
            )
            for t in topics
        ],
    )


@router.get("/visibility", response_model=VisibilityOut)
async def get_visibility(current_user: User = Depends(get_current_user)) -> VisibilityOut:
    return VisibilityOut(
        supervisor_visibility=current_user.supervisor_visibility,
        visibility_changed_at=current_user.visibility_changed_at,
    )


@router.post("/visibility", response_model=VisibilityOut)
async def set_visibility(
    body: SetVisibilityRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VisibilityOut:
    """BDD 3.4 — student opt-in/opt-out toggle.

    Idempotent: setting to the current value is allowed and updates the
    timestamp (so the audit trail still records the click).
    """
    if current_user.tenant_id is not None:
        from atlas.db.tenant_helpers import assert_tenant_writable
        await assert_tenant_writable(current_user.tenant_id, db, current_user)

    new_value = body.visibility
    now = datetime.now(timezone.utc)
    old_value = current_user.supervisor_visibility

    current_user.supervisor_visibility = new_value
    current_user.visibility_changed_at = now
    await db.flush()

    await write_audit(
        db,
        action="user.visibility.toggle",
        actor_id=current_user.id,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        target_type="user",
        target_id=str(current_user.id),
        details={"from": old_value, "to": new_value},
        flush_only=True,
    )
    await db.commit()

    return VisibilityOut(
        supervisor_visibility=new_value,
        visibility_changed_at=now,
    )
