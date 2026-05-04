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
    id: str  # uuid; needed by supervisor drilldown
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
                id=str(t.id),
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


# ─── M4.5.D: coverage report ──────────────────────────────────────────────


class CoverageRow(BaseModel):
    external_id: str
    section: str
    title: str
    coverage_chunks: int
    bucket: str  # "red" | "yellow" | "green"


class CoverageReport(BaseModel):
    program_version: str
    program_status: str
    K_self_check: int
    K_qa: int
    topics: list[CoverageRow]
    summary: dict  # totals per bucket


# Defaults match roadmap §M4.5.D.
_K_SELF_CHECK_DEFAULT = 5
_K_QA_DEFAULT = 2


def _coverage_bucket(n: int, k_qa: int, k_self: int) -> str:
    if n < k_qa:
        return "red"
    if n < k_self:
        return "yellow"
    return "green"


@router.get("/{slug}/coverage", response_model=CoverageReport)
async def coverage_report(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin),
) -> CoverageReport:
    """Per-topic coverage for the active program (BDD 4.4).

    Reads the denormalized `program_topics.coverage_chunks` counter
    (maintained by triggers in M4.5.B) and buckets each topic into
    red / yellow / green relative to the K thresholds:
      red    : coverage < K_qa  (Q&A topic-mode falls back to corpus-wide)
      yellow : K_qa ≤ coverage < K_self (Q&A works, self-check blocked)
      green  : coverage ≥ K_self
    Thresholds come from `tenants.config.coverage` JSONB if present,
    otherwise the M4.5.D defaults (K_qa=2, K_self_check=5).
    """
    tenant = await _resolve_tenant_by_slug(slug, db)
    _ensure_can_manage(tenant, current_user)

    cfg = (tenant.config or {}).get("coverage") or {}
    k_qa = int(cfg.get("k_qa", _K_QA_DEFAULT))
    k_self = int(cfg.get("k_self_check", _K_SELF_CHECK_DEFAULT))

    prog_result = await db.execute(
        select(Program).where(
            Program.tenant_id == tenant.id, Program.status == "active"
        )
    )
    program = prog_result.scalar_one_or_none()
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active program for this tenant",
        )

    topics_result = await db.execute(
        select(ProgramTopic)
        .where(ProgramTopic.program_id == program.id)
        .order_by(ProgramTopic.ordinal)
    )
    rows: list[CoverageRow] = []
    summary = {"red": 0, "yellow": 0, "green": 0}
    for t in topics_result.scalars().all():
        bucket = _coverage_bucket(t.coverage_chunks, k_qa, k_self)
        summary[bucket] += 1
        rows.append(
            CoverageRow(
                external_id=t.external_id,
                section=t.section,
                title=t.title,
                coverage_chunks=t.coverage_chunks,
                bucket=bucket,
            )
        )

    return CoverageReport(
        program_version=program.version,
        program_status=program.status,
        K_self_check=k_self,
        K_qa=k_qa,
        topics=rows,
        summary=summary,
    )


# ─── M4.5.D: quality-score formula on materials ──────────────────────────
# A simple structural heuristic — three components averaged:
#   * fraction of chunks with text length in [200, 2000] characters
#   * fraction of chunks WITHOUT >=4 consecutive newlines (an OCR artifact)
#   * fraction of chunks WITH detectable Cyrillic OR Latin content (≥50%
#     letter-to-total ratio)
# The threshold for low_quality flag lives in tenants.config.quality
# (default 0.6).


def _quality_score_for_chunks(texts: list[str]) -> float:
    if not texts:
        return 0.0

    def _is_reasonable_length(t: str) -> bool:
        n = len(t)
        return 200 <= n <= 2000

    def _no_ocr_artifacts(t: str) -> bool:
        # 4+ consecutive newlines = page-break / OCR garbage marker.
        return "\n\n\n\n" not in t

    def _detect_language(t: str) -> bool:
        # ≥50% characters are letters (cyrillic OR latin) → looks like text.
        if not t:
            return False
        letters = sum(1 for c in t if c.isalpha())
        return letters / max(len(t), 1) >= 0.5

    n = len(texts)
    a = sum(1 for t in texts if _is_reasonable_length(t)) / n
    b = sum(1 for t in texts if _no_ocr_artifacts(t)) / n
    c = sum(1 for t in texts if _detect_language(t)) / n
    return round((a + b + c) / 3, 4)


class QualityScoreOut(BaseModel):
    material_id: str
    filename: str
    quality_score: float
    low_quality: bool
    threshold: float
    components: dict  # {length, no_ocr_artifacts, language}


@router.post(
    "/{slug}/materials/{material_id}/quality-score",
    response_model=QualityScoreOut,
)
async def compute_quality_score(
    slug: str,
    material_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_tenant_admin),
) -> QualityScoreOut:
    """Compute and persist the quality_score for a material (BDD 4.8).

    Heuristic-based; result stored on documents.quality_score. Material
    is flagged as low_quality if score < tenants.config.quality.low_quality_threshold
    (default 0.6). Low-quality materials are NOT removed from retrieval —
    they're surfaced in the tenant-admin UI for manual review.
    """
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

    # Pull chunk texts. Use raw SQL — we don't need ORM hydration overhead
    # for what's potentially a few thousand rows.
    from sqlalchemy import text as sql_text  # local import — small surface

    rows = await db.execute(
        sql_text("SELECT text FROM chunks WHERE document_id = :mid"),
        {"mid": material.id},
    )
    chunk_texts = [r[0] for r in rows.all()]

    score = _quality_score_for_chunks(chunk_texts)

    # Recompute components for transparency in response.
    if chunk_texts:
        n = len(chunk_texts)
        components = {
            "length": round(
                sum(1 for t in chunk_texts if 200 <= len(t) <= 2000) / n, 4
            ),
            "no_ocr_artifacts": round(
                sum(1 for t in chunk_texts if "\n\n\n\n" not in t) / n, 4
            ),
            "language": round(
                sum(
                    1
                    for t in chunk_texts
                    if (sum(1 for c in t if c.isalpha()) / max(len(t), 1)) >= 0.5
                )
                / n,
                4,
            ),
        }
    else:
        components = {"length": 0.0, "no_ocr_artifacts": 0.0, "language": 0.0}

    cfg = (tenant.config or {}).get("quality") or {}
    threshold = float(cfg.get("low_quality_threshold", 0.6))
    low_quality = score < threshold

    material.quality_score = score
    await db.flush()
    await write_audit(
        db,
        action="material.quality_score.compute",
        actor_id=current_user.id,
        actor_role=current_user.role,
        tenant_id=tenant.id,
        target_type="material",
        target_id=str(material.id),
        details={
            "score": score,
            "threshold": threshold,
            "low_quality": low_quality,
            "components": components,
            "n_chunks": len(chunk_texts),
        },
        flush_only=True,
    )
    await db.commit()

    return QualityScoreOut(
        material_id=str(material.id),
        filename=material.filename,
        quality_score=score,
        low_quality=low_quality,
        threshold=threshold,
        components=components,
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
                id=str(t.id),
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
