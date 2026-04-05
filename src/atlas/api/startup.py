import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from atlas.core.config import settings
from atlas.core.security import hash_password
from atlas.core.logging import logger
from atlas.db.models import User, UserRole


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
