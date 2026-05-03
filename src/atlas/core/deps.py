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
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
