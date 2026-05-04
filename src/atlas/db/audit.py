"""Audit log helper (M4.D, BDD 7.1).

Append-only trail of governance-relevant events. Reads happen through
`audit_log` table (model: `atlas.db.models.AuditLog`); writes go through
this single helper to ensure consistent shape and so we can attach
sanitization/observability later in one place.

Conventions for `action` strings — kept hyphen-free for easy filtering:
  tenant.create        — super-admin creates a new tenant
  user.bootstrap       — super-admin seeded from ENV on first start
  user.role.grant      — invite redemption assigns a role to a new user
  user.role.revoke     — tenant-admin revokes an existing role
  user.delete          — soft-delete + anonymization (BDD 7.3)
  personal_data.access — supervisor reads a student's persona-level data
                         (M5 — added when the dashboard ships)
  material.delete      — tenant-admin removes a corpus material
  material.replace     — tenant-admin uploads a new version (M4.5)
  invite.issue         — tenant-admin issues an invite code
  invite.redeem        — invite was redeemed → user.role.grant follows
  privacy.violation_attempt — middleware blocked an unauthorized access
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atlas.db.models import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    actor_id: UUID | None = None,
    actor_role: str | None = None,
    tenant_id: UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
    flush_only: bool = False,
) -> None:
    """Append one audit-log row.

    `flush_only=True` schedules the INSERT but doesn't commit — caller is
    inside a transaction and will commit themselves. Default `False` does
    `commit()` at the end so write_audit-only call sites (e.g. middleware
    handlers that don't otherwise touch DB) are correct standalone.

    Sanitization: this helper does NOT scrub `details`. Caller must avoid
    putting secrets/PII there. For high-volume actions where the caller
    would otherwise dump full request bodies, prefer storing only IDs
    plus a small enum-like "kind" tag.
    """
    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        actor_role=actor_role,
        tenant_id=tenant_id,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        request_id=request_id,
        details=details,
    )
    db.add(entry)
    if flush_only:
        await db.flush()
    else:
        await db.commit()
