import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from atlas.core.config import settings
from atlas.core.security import hash_password
from atlas.core.logging import logger
from atlas.db.models import IngestionJob, User, UserRole


async def seed_admin(db: AsyncSession) -> None:
    """Bootstrap a super-admin from ENV on first start (BDD 4.9).

    Idempotent: when *any* super-admin already exists, ENV is ignored —
    so a re-deploy with a different ADMIN_PASSWORD will NOT silently
    overwrite the live password. Password rotation must go through a
    UI/API path (M4.C will add it as a separate endpoint).
    """
    # Look for any existing super-admin (not just by email — covers the
    # case where someone changes ADMIN_EMAIL on re-deploy).
    result = await db.execute(
        select(User).where(User.role == UserRole.super_admin.value)
    )
    existing_super_admin = result.scalar_one_or_none()
    if existing_super_admin is not None:
        logger.info(
            "admin_seed_skipped",
            reason="super-admin already exists",
            existing_email=existing_super_admin.email,
            env_email=settings.admin_email,
            note="ENV ADMIN_PASSWORD is ignored to prevent silent overwrites",
        )
        return

    admin = User(
        id=uuid.uuid4(),
        email=settings.admin_email,
        hashed_password=hash_password(settings.admin_password),
        role=UserRole.super_admin.value,
        # tenant_id stays NULL — super-admin is cross-tenant.
    )
    db.add(admin)
    await db.commit()
    logger.info("admin_seeded", email=settings.admin_email)


async def reset_stale_jobs(db: AsyncSession) -> None:
    """Mark any jobs stuck in 'running' as failed — happens after server restart."""
    result = await db.execute(
        update(IngestionJob)
        .where(IngestionJob.status == "running")
        .values(status="failed", completed_at=datetime.utcnow())
        .returning(IngestionJob.id)
    )
    stale = result.fetchall()
    if stale:
        logger.warning("stale_jobs_reset", count=len(stale),
                       ids=[str(r[0]) for r in stale])
    await db.commit()
