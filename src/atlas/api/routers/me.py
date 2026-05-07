"""User self-management ('me' endpoints, M5.A).

Currently scoped to:
  * GET  /me — basic profile + visibility flag.
  * GET  /me/visibility — current supervisor_visibility setting.
  * POST /me/visibility — student/supervisor/tenant-admin toggles their
    own opt-in for supervisor analytics (BDD 3.4). The change is logged
    in audit_log so any supervisor access during a covered period can
    be reconstructed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import get_current_user
from atlas.db.audit import write_audit
from atlas.db.models import SupervisorVisibility, Tenant, User
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
