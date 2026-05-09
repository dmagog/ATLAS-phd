import asyncio
import uuid
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.deps import require_admin
from atlas.core.logging import logger
from atlas.db.session import AsyncSessionLocal, get_db
from atlas.db.models import Chunk, Document, IngestionJob, User
from atlas.ingestion.pipeline import RawFile, run_ingestion_job

CORPUS_DIR = Path("/app/corpus")

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Response models ───────────────────────────────────────────────────────────

class IngestionJobStartResponse(BaseModel):
    job_id: str
    status: str
    file_count: int


class IngestionJobStatusResponse(BaseModel):
    job_id: str
    status: str
    accepted_files: list
    rejected_files: list
    progress_info: dict | None = None


class DocumentInfo(BaseModel):
    document_id: str
    title: str
    filename: str
    chunk_count: int
    created_at: str


# ── Background worker ─────────────────────────────────────────────────────────

async def _run_job_background(job_id: str, raw_files: list[RawFile]) -> None:
    """Runs ingestion in a separate DB session so it doesn't block the request."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            logger.error("background_job_not_found", job_id=job_id)
            return
        CORPUS_DIR.mkdir(parents=True, exist_ok=True)
        await run_ingestion_job(db, job, raw_files, CORPUS_DIR)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/ingestion-jobs", response_model=IngestionJobStartResponse)
async def create_ingestion_job(
    background_tasks: BackgroundTasks,
    request: Request,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> IngestionJobStartResponse:
    """Start an ingestion job. Returns immediately with job_id; processing runs in background."""
    from atlas.core.config import settings
    from atlas.db.tenant_helpers import assert_tenant_writable, resolve_tenant_id_for_user

    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    await assert_tenant_writable(tenant_id, db, current_user)

    # Лимиты на размер/количество — защита от memory-DoS. UploadFile.read()
    # держит файл целиком в RAM, поэтому без лимита один 5GB-файл уроняет
    # процесс. Лимиты конфигурируются через UPLOAD_MAX_*-env vars.
    max_file_bytes = settings.upload_max_file_size_mb * 1024 * 1024
    max_total_bytes = settings.upload_max_total_size_mb * 1024 * 1024
    if len(files) > settings.upload_max_files_per_job:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Слишком много файлов в одной задаче "
                f"(макс {settings.upload_max_files_per_job})."
            ),
        )

    job = IngestionJob(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        created_by=current_user.id,
        status="created",
    )
    db.add(job)
    await db.commit()

    raw_files: list[RawFile] = []
    total_bytes = 0
    for upload in files:
        content = await upload.read()
        if len(content) > max_file_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Файл '{upload.filename}' превышает лимит "
                    f"{settings.upload_max_file_size_mb} MB."
                ),
            )
        total_bytes += len(content)
        if total_bytes > max_total_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Суммарный размер файлов превышает лимит "
                    f"{settings.upload_max_total_size_mb} MB."
                ),
            )
        mime = upload.content_type or "application/octet-stream"
        raw_files.append(RawFile(filename=upload.filename or "unknown", content=content, mime_type=mime))

    background_tasks.add_task(_run_job_background, str(job.id), raw_files)

    logger.info("ingestion_job_started", job_id=str(job.id), files=len(raw_files))
    return IngestionJobStartResponse(
        job_id=str(job.id),
        status="created",
        file_count=len(raw_files),
    )


@router.get("/ingestion-jobs/{job_id}", response_model=IngestionJobStatusResponse)
async def get_ingestion_job(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> IngestionJobStatusResponse:
    """Poll ingestion job status. M4.A: scoped to caller's tenant context.

    A bound tenant-admin can only see jobs of their tenant. A super-admin
    sees jobs of the tenant currently selected via `X-Atlas-Tenant`
    (default tenant if header missing).
    """
    from atlas.db.tenant_helpers import resolve_tenant_id_for_user
    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    result = await db.execute(
        select(IngestionJob).where(
            IngestionJob.id == job_id,
            IngestionJob.tenant_id == tenant_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return IngestionJobStatusResponse(
        job_id=str(job.id),
        status=job.status,
        accepted_files=job.accepted_files or [],
        rejected_files=job.rejected_files or [],
        progress_info=job.progress_info,
    )


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[DocumentInfo]:
    """List ingested documents in the caller's tenant (M4.A).

    Bound tenant-admin sees only documents of their tenant. Super-admin
    sees documents of the tenant currently selected via `X-Atlas-Tenant`
    header (default tenant if header is missing).
    """
    from atlas.db.tenant_helpers import resolve_tenant_id_for_user
    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    rows = await db.execute(
        select(
            Document.id,
            Document.title,
            Document.filename,
            Document.created_at,
            func.count(Chunk.id).label("chunk_count"),
        )
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .where(Document.tenant_id == tenant_id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    )
    return [
        DocumentInfo(
            document_id=str(r.id),
            title=r.title,
            filename=r.filename,
            chunk_count=r.chunk_count,
            created_at=r.created_at.strftime("%d.%m.%Y %H:%M"),
        )
        for r in rows
    ]


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> None:
    """Delete a document and its chunks.

    M4.A: only documents of the caller's tenant context can be deleted.
    Bound tenant-admin → own tenant. Super-admin → tenant of `X-Atlas-Tenant`
    (default tenant if header missing). 404 if not found in scope.

    Audit log entry is written for traceability.
    """
    from atlas.db.tenant_helpers import assert_tenant_writable, resolve_tenant_id_for_user
    from atlas.db.audit import write_audit
    from sqlalchemy import delete as sql_delete

    tenant_id = await resolve_tenant_id_for_user(current_user, db, request)
    await assert_tenant_writable(tenant_id, db, current_user)

    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(Document).where(
            Document.id == doc_uuid,
            Document.tenant_id == tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    title = doc.title
    filename = doc.filename
    await db.execute(sql_delete(Chunk).where(Chunk.document_id == doc.id))
    await db.delete(doc)
    await write_audit(
        db,
        action="document.delete",
        actor_id=current_user.id,
        actor_role=current_user.role,
        tenant_id=tenant_id,
        target_type="document",
        target_id=str(doc.id),
        details={"title": title, "filename": filename},
    )
    await db.commit()
    logger.info("document_deleted",
                document_id=str(doc.id), title=title,
                tenant_id=str(tenant_id), actor_id=str(current_user.id))
