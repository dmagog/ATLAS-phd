"""Tenant resolution helpers (M4.A).

For non-super-admin users, tenant_id is taken from the user record. For
super-admin (cross-tenant), we fall back to the 'default' tenant — until
M4.C adds an explicit tenant-context header for super-admin operations.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.db.models import Tenant, User

_DEFAULT_TENANT_ID: UUID | None = None


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


async def resolve_tenant_id_for_user(user: User, db: AsyncSession) -> UUID:
    """Which tenant context does this user act in?

    * Bound users (student / supervisor / tenant-admin) → their `user.tenant_id`.
    * super-admin (tenant_id IS NULL) → the default tenant. M4.C will let
      super-admin operate in a specific tenant via a header; until then
      everything they do lands in default (which is the existing M2 behavior
      for the only admin user that exists today).
    """
    if user.tenant_id is not None:
        return user.tenant_id
    return await get_default_tenant_id(db)
