import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from atlas.core.deps import require_admin
from atlas.db.session import get_db
from atlas.db.models import IngestionJob, User
from atlas.ingestion.pipeline import RawFile, run_ingestion_job

CORPUS_DIR = Path("/app/corpus")

router = APIRouter(prefix="/admin", tags=["admin"])


class IngestionJobResponse(BaseModel):
    job_id: str
    status: str
    accepted_files: list
    rejected_files: list


@router.post("/ingestion-jobs", response_model=IngestionJobResponse)
async def create_ingestion_job(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> IngestionJobResponse:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    job = IngestionJob(id=uuid.uuid4(), created_by=current_user.id)
    db.add(job)
    await db.flush()

    raw_files = []
    for upload in files:
        content = await upload.read()
        mime = upload.content_type or "application/octet-stream"
        raw_files.append(RawFile(filename=upload.filename, content=content, mime_type=mime))

    job = await run_ingestion_job(db, job, raw_files, CORPUS_DIR)

    return IngestionJobResponse(
        job_id=str(job.id),
        status=job.status,
        accepted_files=job.accepted_files,
        rejected_files=job.rejected_files,
    )
