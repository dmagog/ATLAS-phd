"""Tenant resolution helpers (M4.A + M4.C).

Bound users (student/supervisor/tenant-admin) operate in their own tenant.
Super-admin is cross-tenant — by default they fall through to the
'default' tenant, but they can override per-request via the
`X-Atlas-Tenant: <slug>` header (M4.C).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.db.models import Tenant, User, UserRole

_DEFAULT_TENANT_ID: UUID | None = None

# HTTP header for super-admin to operate inside a specific tenant.
TENANT_HEADER = "X-Atlas-Tenant"


async def get_default_tenant_id(db: AsyncSession) -> UUID:
    """Cached lookup of the 'default' tenant ID.

    Cached at module level — the default tenant is created in migration
    0005 and never deleted.
    """
    global _DEFAULT_TENANT_ID
    if _DEFAULT_TENANT_ID is not None:
        return _DEFAULT_TENANT_ID
    result = await db.execute(select(Tenant.id).where(Tenant.slug == "default"))
    tid = result.scalar_one_or_none()
    if tid is None:
        raise RuntimeError(
            "default tenant not found — was migration 0005_m4a_multitenancy applied?"
        )
    _DEFAULT_TENANT_ID = tid
    return tid


async def _tenant_id_from_slug(slug: str, db: AsyncSession) -> UUID:
    """Resolve a tenant slug to its UUID, or 404 if unknown."""
    result = await db.execute(select(Tenant.id).where(Tenant.slug == slug))
    tid = result.scalar_one_or_none()
    if tid is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant not found: {slug}",
        )
    return tid


async def resolve_tenant_id_for_user(
    user: User,
    db: AsyncSession,
    request: Request | None = None,
) -> UUID:
    """Which tenant context does this user act in?

    * Bound users (student / supervisor / tenant-admin) → `user.tenant_id`.
      They cannot override; the X-Atlas-Tenant header is rejected if it
      points at any other tenant.
    * super-admin (tenant_id IS NULL):
      - If `X-Atlas-Tenant: <slug>` is present, use that tenant (404 if
        unknown).
      - Otherwise fall back to the default tenant (M2-era behavior).
    """
    header_slug: str | None = None
    if request is not None:
        # FastAPI lowercases header keys but accepts case-insensitive lookup
        header_slug = request.headers.get(TENANT_HEADER) or request.headers.get(
            TENANT_HEADER.lower()
        )

    if user.role == UserRole.super_admin.value:
        if header_slug:
            return await _tenant_id_from_slug(header_slug, db)
        return await get_default_tenant_id(db)

    # Bound users — return their tenant. If header is set and points to a
    # different tenant, that's an attempt to leave their scope; reject
    # rather than silently ignore.
    if header_slug:
        target = await _tenant_id_from_slug(header_slug, db)
        if target != user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-tenant access forbidden for non-super-admin",
            )
    if user.tenant_id is None:
        # Defensive: a non-super-admin without a tenant_id is a data corruption.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User missing tenant binding",
        )
    return user.tenant_id
