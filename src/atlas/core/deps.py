from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from atlas.core.security import decode_token
from atlas.db.session import get_db
from atlas.db.models import User, UserRole

bearer = HTTPBearer()


# Roles that have admin privileges (corpus management, ingestion, etc).
# super-admin: cross-tenant; tenant-admin: only own tenant (enforced separately
# in M4.C RBAC matrix). Endpoints calling require_admin in M2 era assumed a
# single-tenant world — they keep working for super-admin and (post-M4.C)
# tenant-admin within their tenant.
_ADMIN_ROLES = {UserRole.super_admin.value, UserRole.tenant_admin.value}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    # M4.C JWT versioning (BDD 7.5): role revocation / forced logout bumps
    # users.jwt_version. Tokens issued before that point carry stale `jv`
    # and are rejected here. Tokens minted before M4.C didn't have `jv`
    # — treat missing `jv` as version 1 to avoid breaking existing sessions
    # at first deploy of this change.
    token_jv = int(payload.get("jv", 1))
    if token_jv != user.jwt_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked — please sign in again",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
