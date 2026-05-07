#!/usr/bin/env python3
"""seed_demo_users.py — Phase 6.1.

Создаёт реалистичных пользователей в тенанте `optics-kafedra` для
демонстрации защиты:
  * 1 tenant-admin    (Андреев Д. С., admin@optics.demo)
  * 1 supervisor       (Васильев Н. К., vasiliev@optics.demo)
  * 12 студентов с русскими ФИО (соответствуют sample data в wireframes
    и styleguide для непрерывности)

Все пароли установлены в `demo` — это локальный закрытый пилот, не
production-credentials. ENV PASSWORD_OVERRIDE может задать другой пароль.

ИДЕМПОТЕНТЕН: пользователи с уже существующим email пропускаются.

Запуск изнутри docker:
    docker compose exec -T app python3 scripts/seed_demo_users.py

Из хоста (через docker exec):
    docker compose exec app python3 scripts/seed_demo_users.py
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import uuid
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure /app is on path (script lives at /app/scripts/, src at /app/src/).
sys.path.insert(0, "/app/src")

from atlas.core.security import hash_password
from atlas.db.audit import write_audit
from atlas.db.models import SupervisorVisibility, Tenant, User, UserRole
from atlas.db.session import AsyncSessionLocal


# ── Demo user roster ─────────────────────────────────────────────────────
class DemoUser(NamedTuple):
    email: str
    display_name: str   # informational, used as audit detail
    role: str           # UserRole value
    visibility: str     # SupervisorVisibility value


PASSWORD = os.getenv("DEMO_PASSWORD", "demo")
TENANT_SLUG = "optics-kafedra"

ROSTER: list[DemoUser] = [
    DemoUser("admin@optics.demo",     "Андреев Д. С.",    UserRole.tenant_admin.value, SupervisorVisibility.show.value),
    DemoUser("vasiliev@optics.demo",  "Васильев Н. К.",   UserRole.supervisor.value,   SupervisorVisibility.show.value),

    # 12 студентов. Половина opted-in для демонстрации privacy mask.
    DemoUser("ivanov@optics.demo",       "Иванов А. М.",        UserRole.student.value, SupervisorVisibility.show.value),
    DemoUser("petrova@optics.demo",      "Петрова К. С.",       UserRole.student.value, SupervisorVisibility.show.value),
    DemoUser("sidorov@optics.demo",      "Сидоров Д. Н.",       UserRole.student.value, SupervisorVisibility.anonymous.value),
    DemoUser("kozlova@optics.demo",      "Козлова Е. В.",       UserRole.student.value, SupervisorVisibility.show.value),
    DemoUser("morozov@optics.demo",      "Морозов П. И.",       UserRole.student.value, SupervisorVisibility.anonymous.value),
    DemoUser("volkov@optics.demo",       "Волков С. Р.",        UserRole.student.value, SupervisorVisibility.show.value),
    DemoUser("lebedeva@optics.demo",     "Лебедева Н. О.",      UserRole.student.value, SupervisorVisibility.anonymous.value),
    DemoUser("sokolov@optics.demo",      "Соколов А. Д.",       UserRole.student.value, SupervisorVisibility.show.value),
    DemoUser("raskolnikov@optics.demo",  "Раскольников А. И.",  UserRole.student.value, SupervisorVisibility.anonymous.value),
    DemoUser("zaytseva@optics.demo",     "Зайцева В. Б.",       UserRole.student.value, SupervisorVisibility.show.value),
    DemoUser("belyaev@optics.demo",      "Беляев М. К.",        UserRole.student.value, SupervisorVisibility.anonymous.value),
    DemoUser("egorov@optics.demo",       "Егоров Т. С.",        UserRole.student.value, SupervisorVisibility.show.value),
]


async def get_pilot_tenant(db: AsyncSession) -> Tenant:
    t = (await db.execute(select(Tenant).where(Tenant.slug == TENANT_SLUG))).scalar_one_or_none()
    if t is None:
        raise SystemExit(
            f"Tenant '{TENANT_SLUG}' not found. "
            f"Создайте его (через alembic seed или /tenants POST) перед запуском seed_demo_users."
        )
    return t


async def find_super_admin(db: AsyncSession) -> User | None:
    return (
        await db.execute(select(User).where(User.role == UserRole.super_admin.value))
    ).scalar_one_or_none()


async def seed() -> None:
    print(f"🌱 seed_demo_users.py — tenant={TENANT_SLUG}")
    print()

    async with AsyncSessionLocal() as db:
        tenant = await get_pilot_tenant(db)
        actor = await find_super_admin(db)
        actor_id = actor.id if actor else None
        actor_role = actor.role if actor else "system"

        created = 0
        skipped = 0
        skipped_emails: list[str] = []

        for u in ROSTER:
            existing = (
                await db.execute(select(User).where(User.email == u.email))
            ).scalar_one_or_none()
            if existing is not None:
                skipped += 1
                skipped_emails.append(u.email)
                continue

            user = User(
                id=uuid.uuid4(),
                email=u.email,
                hashed_password=hash_password(PASSWORD),
                role=u.role,
                tenant_id=tenant.id,
                supervisor_visibility=u.visibility,
            )
            db.add(user)
            await db.flush()

            await write_audit(
                db,
                action="user.create",
                actor_id=actor_id,
                actor_role=actor_role,
                tenant_id=tenant.id,
                target_type="user",
                target_id=str(user.id),
                details={
                    "email": u.email,
                    "display_name": u.display_name,
                    "role": u.role,
                    "source": "seed_demo_users",
                    "visibility": u.visibility,
                },
                flush_only=True,
            )

            created += 1
            print(f"  + {u.role:14s} {u.email:30s} {u.display_name}")

        await db.commit()
        print()
        print(f"✓ created: {created}")
        print(f"✓ skipped (already exists): {skipped}")
        if skipped_emails:
            print(f"   {', '.join(skipped_emails[:6])}{'…' if len(skipped_emails) > 6 else ''}")
        print()
        print(f"Login template:")
        print(f"  email:    <user>@optics.demo")
        print(f"  password: {PASSWORD}")
        print()
        print(f"Тестовые роли:")
        print(f"  tenant-admin: admin@optics.demo")
        print(f"  supervisor:   vasiliev@optics.demo")
        print(f"  student:      ivanov@optics.demo (или любой *@optics.demo)")


if __name__ == "__main__":
    asyncio.run(seed())
