"""Tenant management (M4.D, BDD 8.3 + 8.1).

Super-admin-only operations. The bound roles never see this surface.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import require_super_admin
from atlas.db.audit import write_audit
from atlas.db.models import Tenant, User
from atlas.db.session import get_db

router = APIRouter(prefix="/tenants", tags=["tenants"])

# slug must be lowercase letters/digits/hyphens (URL-safe).
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class CreateTenantRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=255)


class TenantOut(BaseModel):
    id: str
    slug: str
    display_name: str
    status: str
    created_at: datetime


@router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: CreateTenantRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin),
) -> TenantOut:
    if not _SLUG_RE.match(body.slug):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="slug must match ^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$",
        )

    # Conflict on duplicate slug.
    existing = await db.execute(select(Tenant).where(Tenant.slug == body.slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with slug '{body.slug}' already exists",
        )

    tenant = Tenant(
        id=uuid.uuid4(),
        slug=body.slug,
        display_name=body.display_name,
        status="active",
        config={},
        created_by=current_user.id,
    )
    db.add(tenant)
    await db.flush()

    await write_audit(
        db,
        action="tenant.create",
        actor_id=current_user.id,
        actor_role=current_user.role,
        tenant_id=tenant.id,  # the new tenant itself is the target
        target_type="tenant",
        target_id=str(tenant.id),
        details={"slug": tenant.slug, "display_name": tenant.display_name},
        flush_only=True,
    )
    await db.commit()
    await db.refresh(tenant)

    return TenantOut(
        id=str(tenant.id),
        slug=tenant.slug,
        display_name=tenant.display_name,
        status=tenant.status,
        created_at=tenant.created_at,
    )


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin),
) -> list[TenantOut]:
    """List all tenants (super-admin only). BDD 8.3 prerequisite."""
    result = await db.execute(select(Tenant).order_by(Tenant.created_at))
    tenants = result.scalars().all()
    return [
        TenantOut(
            id=str(t.id),
            slug=t.slug,
            display_name=t.display_name,
            status=t.status,
            created_at=t.created_at,
        )
        for t in tenants
    ]
