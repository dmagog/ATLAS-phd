"""Invite-flow endpoints (M4.C, BDD 4.6 + 4.10).

A tenant-admin (or super-admin) generates an invite-link bound to a
specific role. The unredeemed invite is stored with an expiry. Any new
user can register via the invite, recording explicit consent.

Endpoints:
  POST   /invites                  — issue an invite (tenant-admin/super-admin)
  GET    /invites                  — list outstanding invites in the caller's tenant
  POST   /invites/{code}/redeem    — register a new user (no auth required)
"""
from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import get_current_user, require_tenant_admin
from atlas.core.security import create_access_token, hash_password
from atlas.db.models import InviteCode, User, UserRole
from atlas.db.session import get_db
from atlas.db.tenant_helpers import resolve_tenant_id_for_user

router = APIRouter(prefix="/invites", tags=["invites"])


# A redeemable role from the invite — never super-admin (super-admin is
# bootstrapped, not invited).
_INVITABLE_ROLES = {
    UserRole.tenant_admin.value,
    UserRole.supervisor.value,
    UserRole.student.value,
}

# Default invite TTL — roadmap M4.C says 7 days.
DEFAULT_TTL_DAYS = 7


def _generate_code(n: int = 32) -> str:
    """Cryptographically random URL-safe code."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


# ─── Issue ────────────────────────────────────────────────────────────────────


class IssueInviteRequest(BaseModel):
    role: Literal["tenant-admin", "supervisor", "student"]
    expires_in_days: int | None = None  # None → DEFAULT_TTL_DAYS


class InviteResponse(BaseModel):
    code: str
    role: str
    tenant_id: str
    expires_at: datetime | None
    redeemed_at: datetime | None
    redeemed_by: str | None


@router.post("", response_model=InviteResponse, status_code=201)
async def issue_invite(
    body: IssueInviteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin),
) -> InviteResponse:
    if body.role not in _INVITABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="role must be tenant-admin, supervisor, or student",
        )
    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    ttl = body.expires_in_days if body.expires_in_days is not None else DEFAULT_TTL_DAYS
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl)

    code = _generate_code()
    invite = InviteCode(
        code=code,
        tenant_id=tenant_id,
        role=body.role,
        created_by=current_user.id,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.flush()

    # Audit (BDD 7.1).
    from atlas.db.audit import write_audit
    await write_audit(
        db,
        action="invite.issue",
        actor_id=current_user.id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        target_type="invite",
        target_id=code,
        details={"role": body.role, "expires_at": expires_at.isoformat()},
        flush_only=True,
    )
    await db.commit()

    return InviteResponse(
        code=code,
        role=body.role,
        tenant_id=str(tenant_id),
        expires_at=expires_at,
        redeemed_at=None,
        redeemed_by=None,
    )


# ─── List ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[InviteResponse])
async def list_invites(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin),
) -> list[InviteResponse]:
    """List outstanding invites scoped to the caller's tenant.

    Note: codes are visible in this listing — by design, since a tenant-admin
    is the issuer and may need to re-share the link.
    """
    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    result = await db.execute(
        select(InviteCode).where(InviteCode.tenant_id == tenant_id)
    )
    invites = result.scalars().all()
    return [
        InviteResponse(
            code=i.code,
            role=i.role,
            tenant_id=str(i.tenant_id),
            expires_at=i.expires_at,
            redeemed_at=i.redeemed_at,
            redeemed_by=str(i.redeemed_by) if i.redeemed_by else None,
        )
        for i in invites
    ]


# ─── Redeem ───────────────────────────────────────────────────────────────────


class RedeemRequest(BaseModel):
    email: EmailStr
    password: str
    consent_to_data_processing: bool


class RedeemResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    tenant_id: str
    role: str


@router.post("/{code}/redeem", response_model=RedeemResponse)
async def redeem_invite(
    code: str,
    body: RedeemRequest,
    db: AsyncSession = Depends(get_db),
) -> RedeemResponse:
    """Register a new user via an invite (BDD 4.6, 4.10).

    Single-use: the invite is marked redeemed and cannot be reused. Consent
    on data processing is mandatory — the BDD-4.10 contract stores
    `consent_recorded_at`. Returns a fresh access token so the new user is
    immediately authenticated.
    """
    if not body.consent_to_data_processing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Consent to data processing is required (BDD 4.10)",
        )

    result = await db.execute(select(InviteCode).where(InviteCode.code == code))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    now = datetime.now(timezone.utc)
    if invite.redeemed_at is not None:
        # Tell the client this code was used; 410 Gone matches the lifecycle.
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite already redeemed")
    if invite.expires_at is not None and invite.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite expired")

    # Reject if email already exists.
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    new_user = User(
        id=uuid.uuid4(),
        email=body.email,
        hashed_password=hash_password(body.password),
        role=invite.role,
        tenant_id=invite.tenant_id,
        consent_recorded_at=now,
        jwt_version=1,
    )
    db.add(new_user)
    # Flush so the user row is INSERTed before we UPDATE invite.redeemed_by;
    # otherwise the FK constraint fires on commit (Postgres orders them by
    # what SQLAlchemy emits, not by FK direction).
    await db.flush()

    invite.redeemed_at = now
    invite.redeemed_by = new_user.id

    # Audit (BDD 7.1): two events — invite redeemed + role granted to user.
    from atlas.db.audit import write_audit
    await write_audit(
        db,
        action="invite.redeem",
        actor_id=new_user.id,
        actor_role=new_user.role,
        tenant_id=invite.tenant_id,
        target_type="invite",
        target_id=invite.code,
        details={"role": invite.role, "consent_recorded_at": now.isoformat()},
        flush_only=True,
    )
    await write_audit(
        db,
        action="user.role.grant",
        actor_id=invite.created_by,
        actor_role=None,  # creator's role at issue time isn't tracked here
        tenant_id=invite.tenant_id,
        target_type="user",
        target_id=str(new_user.id),
        details={"granted_role": new_user.role, "via_invite": invite.code},
        flush_only=True,
    )

    await db.commit()
    await db.refresh(new_user)

    token = create_access_token(str(new_user.id), new_user.role, new_user.jwt_version)
    return RedeemResponse(
        access_token=token,
        user_id=str(new_user.id),
        tenant_id=str(new_user.tenant_id),
        role=new_user.role,
    )
