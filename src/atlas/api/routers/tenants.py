"""Tenant management (M4.D + M4.5).

Super-admin handles tenant lifecycle (create / list).
Tenant-admin (and super-admin) handles per-tenant content: programs,
materials, etc.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import require_super_admin, require_tenant_admin
from atlas.db.audit import write_audit
from atlas.db.models import (
    Document,
    MaterialTopic,
    Program,
    ProgramTopic,
    Tenant,
    User,
)
from atlas.db.session import get_db
from atlas.db.tenant_helpers import resolve_tenant_id_for_user
from atlas.programs.parser import ProgramParseError, parse_program

router = APIRouter(prefix="/tenants", tags=["tenants"])

# slug must be lowercase letters/digits/hyphens (URL-safe).
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class CreateTenantRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=255)


class TenantOut(BaseModel):
    id: str
    slug: str
    display_name: str
    status: str
    created_at: datetime


@router.post("", response_model=TenantOut, status_code=201)
async def create_tenant(
    body: CreateTenantRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin),
) -> TenantOut:
    if not _SLUG_RE.match(body.slug):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="slug must match ^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$",
        )

    # Conflict on duplicate slug.
    existing = await db.execute(select(Tenant).where(Tenant.slug == body.slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with slug '{body.slug}' already exists",
        )

    tenant = Tenant(
        id=uuid.uuid4(),
        slug=body.slug,
        display_name=body.display_name,
        status="active",
        config={},
        created_by=current_user.id,
    )
    db.add(tenant)
    await db.flush()

    await write_audit(
        db,
        action="tenant.create",
        actor_id=current_user.id,
        actor_role=current_user.role,
        tenant_id=tenant.id,  # the new tenant itself is the target
        target_type="tenant",
        target_id=str(tenant.id),
        details={"slug": tenant.slug, "display_name": tenant.display_name},
        flush_only=True,
    )
    await db.commit()
    await db.refresh(tenant)

    return TenantOut(
        id=str(tenant.id),
        slug=tenant.slug,
        display_name=tenant.display_name,
        status=tenant.status,
        created_at=tenant.created_at,
    )


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin),
) -> list[TenantOut]:
    """List all tenants (super-admin only). BDD 8.3 prerequisite."""
    result = await db.execute(select(Tenant).order_by(Tenant.created_at))
    tenants = result.scalars().all()
    return [
        TenantOut(
            id=str(t.id),
            slug=t.slug,
            display_name=t.display_name,
            status=t.status,
            created_at=t.created_at,
        )
        for t in tenants
    ]


# ─── M4.5.A: program upload ───────────────────────────────────────────────


class TopicOut(BaseModel):
    external_id: str
    section: str
    title: str
    ordinal: int
    key_concepts: list[str]
    coverage_chunks: int


class ProgramOut(BaseModel):
    id: str
    tenant_slug: str
    version: str
    status: str
    ratified_at: date | None
    loaded_at: datetime
    topics: list[TopicOut]


async def _resolve_tenant_by_slug(slug: str, db: AsyncSession) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    t = result.scalar_one_or_none()
    if t is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Tenant not found: {slug}"
        )
    return t


def _ensure_can_manage(tenant: Tenant, user: User) -> None:
    """Tenant-admin may manage only their own tenant; super-admin may manage any.
    """
    if user.role == "super-admin":
        return
    if user.tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant management forbidden",
        )


@router.post("/{slug}/program", response_model=ProgramOut, status_code=201)
async def upload_program(
    slug: str,
    body: dict,  # {"text": "<full program.md content>"}
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin),
) -> ProgramOut:
    """Upload a program.md as raw text and replace any existing active
    program for the tenant (BDD 4.2 + 4.7).

    On a clean tenant: 201 with the new program.
    When an active program already exists: it's archived (status='archived')
    and a new active one is loaded. Existing attempts/sessions referencing
    the archived program's topics keep working (FK RESTRICT, BDD 7.4).
    """
    if not isinstance(body, dict) or "text" not in body or not isinstance(body["text"], str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Body must be {"text": "<program.md content>"}',
        )
    tenant = await _resolve_tenant_by_slug(slug, db)
    _ensure_can_manage(tenant, current_user)

    try:
        parsed = parse_program(body["text"])
    except ProgramParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid program.md: {exc}",
        )

    if parsed.tenant_slug != tenant.slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"frontmatter tenant_slug='{parsed.tenant_slug}' does not match "
                f"URL slug '{tenant.slug}'"
            ),
        )

    # Archive existing active program (if any).
    existing = await db.execute(
        select(Program).where(Program.tenant_id == tenant.id, Program.status == "active")
    )
    archived_id: str | None = None
    for old in existing.scalars().all():
        old.status = "archived"
        archived_id = str(old.id)

    # Insert new active program.
    new_program = Program(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        version=parsed.program_version,
        status="active",
        loaded_by=current_user.id,
    )
    db.add(new_program)
    await db.flush()

    for topic in parsed.topics:
        db.add(
            ProgramTopic(
                id=uuid.uuid4(),
                program_id=new_program.id,
                external_id=topic.external_id,
                section=topic.section,
                title=topic.title,
                ordinal=topic.ordinal,
                key_concepts=topic.key_concepts,
            )
        )
    await db.flush()

    await write_audit(
        db,
        action="program.upload",
        actor_id=current_user.id,
        actor_role=current_user.role,
        tenant_id=tenant.id,
        target_type="program",
        target_id=str(new_program.id),
        details={
            "version": parsed.program_version,
            "topics_count": len(parsed.topics),
            "archived_program_id": archived_id,
        },
        flush_only=True,
    )
    await db.commit()
    await db.refresh(new_program)

    # Load topics for response.
    topics_result = await db.execute(
        select(ProgramTopic)
        .where(ProgramTopic.program_id == new_program.id)
        .order_by(ProgramTopic.ordinal)
    )
    topic_rows = topics_result.scalars().all()

    return ProgramOut(
        id=str(new_program.id),
        tenant_slug=tenant.slug,
        version=new_program.version,
        status=new_program.status,
        ratified_at=parsed.ratified_at,
        loaded_at=new_program.loaded_at,
        topics=[
            TopicOut(
                external_id=t.external_id,
                section=t.section,
                title=t.title,
                ordinal=t.ordinal,
                key_concepts=list(t.key_concepts or []),
                coverage_chunks=t.coverage_chunks,
            )
            for t in topic_rows
        ],
    )


# ─── M4.5.C: attach materials to topics ──────────────────────────────────


class AttachTopicsRequest(BaseModel):
    """external_ids of topics in the active program (e.g. ["1.3", "2.1"]).

    Idempotent: re-posting the same set is a no-op. Sending an empty list
    detaches the material from all topics.
    """

    topic_external_ids: list[str]


class MaterialTopicsOut(BaseModel):
    material_id: str
    filename: str
    topic_external_ids: list[str]


@router.post(
    "/{slug}/materials/{material_id}/topics",
    response_model=MaterialTopicsOut,
)
async def attach_material_topics(
    slug: str,
    material_id: str,
    body: AttachTopicsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin),
) -> MaterialTopicsOut:
    """Set the topics that a material belongs to (BDD 4.3, BDD 1.2 retrieval).

    The trigger `material_topics_sync_chunk_topics` (M4.5.B) propagates
    the change to chunk_topics for every chunk in the material.

    Idempotent — POSTing the same set leaves DB unchanged.
    """
    tenant = await _resolve_tenant_by_slug(slug, db)
    _ensure_can_manage(tenant, current_user)

    # Material must exist in this tenant.
    try:
        material_uuid = uuid.UUID(material_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"material_id is not a valid UUID: {material_id}",
        )
    mat_result = await db.execute(
        select(Document).where(
            Document.id == material_uuid, Document.tenant_id == tenant.id
        )
    )
    material = mat_result.scalar_one_or_none()
    if material is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material not found in this tenant",
        )

    # Resolve external_ids → topic_id within the tenant's active program.
    if body.topic_external_ids:
        active_prog_result = await db.execute(
            select(Program).where(
                Program.tenant_id == tenant.id, Program.status == "active"
            )
        )
        active_prog = active_prog_result.scalar_one_or_none()
        if active_prog is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No active program — upload program.md before attaching topics",
            )
        topics_result = await db.execute(
            select(ProgramTopic).where(
                ProgramTopic.program_id == active_prog.id,
                ProgramTopic.external_id.in_(body.topic_external_ids),
            )
        )
        topics = topics_result.scalars().all()
        found_eids = {t.external_id for t in topics}
        missing = set(body.topic_external_ids) - found_eids
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown external_ids in active program: {sorted(missing)}",
            )
        target_topic_ids = {t.id for t in topics}
    else:
        target_topic_ids = set()

    # Read current set, compute delta — issue minimum INSERT/DELETE so
    # the trigger doesn't fire spuriously.
    current_result = await db.execute(
        select(MaterialTopic).where(MaterialTopic.material_id == material.id)
    )
    current_topic_ids = {row.topic_id for row in current_result.scalars().all()}

    to_add = target_topic_ids - current_topic_ids
    to_remove = current_topic_ids - target_topic_ids

    for tid in to_add:
        db.add(MaterialTopic(material_id=material.id, topic_id=tid))
    if to_remove:
        from sqlalchemy import delete as sa_delete

        await db.execute(
            sa_delete(MaterialTopic).where(
                MaterialTopic.material_id == material.id,
                MaterialTopic.topic_id.in_(to_remove),
            )
        )

    if to_add or to_remove:
        await db.flush()
        await write_audit(
            db,
            action="material.topics.set",
            actor_id=current_user.id,
            actor_role=current_user.role,
            tenant_id=tenant.id,
            target_type="material",
            target_id=str(material.id),
            details={
                "topic_external_ids": sorted(body.topic_external_ids),
                "added_count": len(to_add),
                "removed_count": len(to_remove),
            },
            flush_only=True,
        )
    await db.commit()

    return MaterialTopicsOut(
        material_id=str(material.id),
        filename=material.filename,
        topic_external_ids=sorted(body.topic_external_ids),
    )


@router.get(
    "/{slug}/materials/{material_id}/topics",
    response_model=MaterialTopicsOut,
)
async def get_material_topics(
    slug: str,
    material_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin),
) -> MaterialTopicsOut:
    """List topics this material is attached to (their external_ids)."""
    tenant = await _resolve_tenant_by_slug(slug, db)
    _ensure_can_manage(tenant, current_user)
    try:
        material_uuid = uuid.UUID(material_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"material_id is not a valid UUID: {material_id}",
        )
    mat_result = await db.execute(
        select(Document).where(
            Document.id == material_uuid, Document.tenant_id == tenant.id
        )
    )
    material = mat_result.scalar_one_or_none()
    if material is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material not found in this tenant",
        )

    # Get external_ids via JOIN.
    result = await db.execute(
        select(ProgramTopic.external_id)
        .join(MaterialTopic, MaterialTopic.topic_id == ProgramTopic.id)
        .where(MaterialTopic.material_id == material.id)
    )
    eids = sorted(r[0] for r in result.all())
    return MaterialTopicsOut(
        material_id=str(material.id),
        filename=material.filename,
        topic_external_ids=eids,
    )


@router.get("/{slug}/program", response_model=ProgramOut | None)
async def get_active_program(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin),
) -> ProgramOut | None:
    """Get the currently active program for a tenant (or None if none loaded)."""
    tenant = await _resolve_tenant_by_slug(slug, db)
    _ensure_can_manage(tenant, current_user)
    result = await db.execute(
        select(Program).where(Program.tenant_id == tenant.id, Program.status == "active")
    )
    program = result.scalar_one_or_none()
    if program is None:
        return None
    topics_result = await db.execute(
        select(ProgramTopic)
        .where(ProgramTopic.program_id == program.id)
        .order_by(ProgramTopic.ordinal)
    )
    topic_rows = topics_result.scalars().all()
    return ProgramOut(
        id=str(program.id),
        tenant_slug=tenant.slug,
        version=program.version,
        status=program.status,
        ratified_at=None,  # we don't persist ratified_at in DB; only in source_doc
        loaded_at=program.loaded_at,
        topics=[
            TopicOut(
                external_id=t.external_id,
                section=t.section,
                title=t.title,
                ordinal=t.ordinal,
                key_concepts=list(t.key_concepts or []),
                coverage_chunks=t.coverage_chunks,
            )
            for t in topic_rows
        ],
    )
