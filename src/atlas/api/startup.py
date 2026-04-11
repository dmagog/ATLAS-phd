import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from atlas.core.config import settings
from atlas.core.security import hash_password
from atlas.core.logging import logger
from atlas.db.models import IngestionJob, User, UserRole


async def seed_admin(db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.email == settings.admin_email))
    if result.scalar_one_or_none():
        return
    admin = User(
        id=uuid.uuid4(),
        email=settings.admin_email,
        hashed_password=hash_password(settings.admin_password),
        role=UserRole.admin,
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
