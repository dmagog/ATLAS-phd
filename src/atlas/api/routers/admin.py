import asyncio
import uuid
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
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
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> IngestionJobStartResponse:
    """Start an ingestion job. Returns immediately with job_id; processing runs in background."""
    job = IngestionJob(id=uuid.uuid4(), created_by=current_user.id, status="created")
    db.add(job)
    await db.commit()

    raw_files: list[RawFile] = []
    for upload in files:
        content = await upload.read()
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> IngestionJobStatusResponse:
    """Poll ingestion job status."""
    result = await db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[DocumentInfo]:
    """List all ingested documents with chunk counts."""
    rows = await db.execute(
        select(
            Document.id,
            Document.title,
            Document.filename,
            Document.created_at,
            func.count(Chunk.id).label("chunk_count"),
        )
        .outerjoin(Chunk, Chunk.document_id == Document.id)
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
