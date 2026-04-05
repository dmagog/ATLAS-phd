"""
Ingestion pipeline: accept → extract → normalize → chunk → embed → index
"""
import hashlib
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from pypdf import PdfReader
from docx import Document as DocxDocument
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.config import settings
from atlas.core.logging import logger
from atlas.db.models import Chunk, Document, IngestionJob


SUPPORTED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}

CHUNK_MIN = 800
CHUNK_MAX = 1200
CHUNK_OVERLAP = 150


@dataclass
class FileResult:
    filename: str
    status: str  # "accepted" | "rejected" | "processed" | "failed"
    reason: Optional[str] = None
    document_id: Optional[str] = None
    chunks_created: int = 0


@dataclass
class RawFile:
    filename: str
    content: bytes
    mime_type: str


# ── Stage 1: Accept ──────────────────────────────────────────────────────────

def accept_file(raw: RawFile) -> tuple[bool, str]:
    """Validate MIME type. Returns (ok, reason_code)."""
    if raw.mime_type not in SUPPORTED_MIME_TYPES:
        return False, "UNSUPPORTED_FORMAT"
    if len(raw.content) == 0:
        return False, "EMPTY_FILE"
    return True, ""


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# ── Stage 2: Extract ─────────────────────────────────────────────────────────

def extract_text(raw: RawFile) -> str:
    if raw.mime_type == "application/pdf":
        return _extract_pdf(raw.content)
    if raw.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx(raw.content)
    # txt / md — decode as utf-8
    return raw.content.decode("utf-8", errors="replace")


def _extract_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n\n".join(pages)


def _extract_docx(content: bytes) -> str:
    doc = DocxDocument(io.BytesIO(content))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


# ── Stage 3: Normalize ───────────────────────────────────────────────────────

_SUSPICIOUS = re.compile(r"(ignore previous instructions|system prompt|disregard)", re.IGNORECASE)


def normalize(text: str) -> str:
    # Collapse excessive whitespace while preserving paragraph breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return text


def has_suspicious_patterns(text: str) -> bool:
    return bool(_SUSPICIOUS.search(text))


# ── Stage 4: Chunk ───────────────────────────────────────────────────────────

def chunk_text(text: str) -> list[str]:
    """
    Split text into chunks of CHUNK_MIN–CHUNK_MAX chars with CHUNK_OVERLAP overlap.
    Tries to split at paragraph boundaries first, then at sentence boundaries.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= CHUNK_MAX:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            # Para itself might exceed CHUNK_MAX — split by sentences
            if len(para) > CHUNK_MAX:
                chunks.extend(_split_long_para(para))
                current = ""
            else:
                # Start new chunk with overlap from previous chunk tail
                overlap_text = current[-CHUNK_OVERLAP:] if current else ""
                current = (overlap_text + "\n\n" + para).strip() if overlap_text else para

    if current and len(current) >= CHUNK_MIN // 2:
        chunks.append(current)
    elif current and chunks:
        chunks[-1] = chunks[-1] + "\n\n" + current

    return chunks


def _split_long_para(para: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", para)
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 1 <= CHUNK_MAX:
            current = (current + " " + sent).strip()
        else:
            if current:
                chunks.append(current)
            current = sent
    if current:
        chunks.append(current)
    return chunks


# ── Stage 5: Embed ───────────────────────────────────────────────────────────

async def embed_chunks(texts: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.embeddings_url}/embed",
            json={"texts": texts},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


# ── Stage 6: Index ───────────────────────────────────────────────────────────

async def index_document(
    db: AsyncSession,
    raw: RawFile,
    sha256: str,
    chunks: list[str],
    embeddings: list[list[float]],
    file_path: str,
    job_id: str,
) -> Document:
    doc = Document(
        id=uuid.uuid4(),
        title=Path(raw.filename).stem,
        filename=raw.filename,
        sha256=sha256,
        file_path=file_path,
        mime_type=raw.mime_type,
    )
    db.add(doc)
    await db.flush()

    for i, (text, embedding) in enumerate(zip(chunks, embeddings)):
        chunk = Chunk(
            id=uuid.uuid4(),
            document_id=doc.id,
            chunk_index=i,
            text=text,
            embedding=embedding,
        )
        db.add(chunk)

    await db.commit()
    logger.info("document_indexed", document_id=str(doc.id), filename=raw.filename, chunks=len(chunks), job_id=job_id)
    return doc


# ── Orchestrator ─────────────────────────────────────────────────────────────

async def process_file(
    db: AsyncSession,
    raw: RawFile,
    corpus_dir: Path,
    job_id: str,
) -> FileResult:
    # Stage 1: Accept
    ok, reason = accept_file(raw)
    if not ok:
        return FileResult(filename=raw.filename, status="rejected", reason=reason)

    # Idempotency check
    sha256 = compute_sha256(raw.content)
    existing = await db.execute(select(Document).where(Document.sha256 == sha256))
    if existing.scalar_one_or_none():
        return FileResult(filename=raw.filename, status="rejected", reason="DUPLICATE")

    try:
        # Stage 2: Extract
        text = extract_text(raw)
        if not text.strip():
            return FileResult(filename=raw.filename, status="rejected", reason="EMPTY_CONTENT")

        # Stage 3: Normalize
        text = normalize(text)
        if has_suspicious_patterns(text):
            logger.warning("suspicious_content_detected", filename=raw.filename, job_id=job_id)

        # Stage 4: Chunk
        chunks = chunk_text(text)
        if not chunks:
            return FileResult(filename=raw.filename, status="failed", reason="CHUNKING_FAILED")

        # Stage 5: Embed
        embeddings = await embed_chunks(chunks)

        # Save file to corpus dir
        file_path = str(corpus_dir / raw.filename)
        (corpus_dir / raw.filename).write_bytes(raw.content)

        # Stage 6: Index
        doc = await index_document(db, raw, sha256, chunks, embeddings, file_path, job_id)

        return FileResult(
            filename=raw.filename,
            status="processed",
            document_id=str(doc.id),
            chunks_created=len(chunks),
        )

    except Exception as exc:
        logger.error("ingestion_file_failed", filename=raw.filename, error=str(exc), job_id=job_id)
        return FileResult(filename=raw.filename, status="failed", reason="PROCESSING_ERROR")


async def run_ingestion_job(
    db: AsyncSession,
    job: IngestionJob,
    files: list[RawFile],
    corpus_dir: Path,
) -> IngestionJob:
    job.status = "running"
    await db.commit()

    accepted = []
    rejected = []

    for raw in files:
        result = await process_file(db, raw, corpus_dir, str(job.id))
        entry = {"filename": result.filename, "reason": result.reason}
        if result.status in ("processed", "accepted"):
            entry["document_id"] = result.document_id
            entry["chunks_created"] = result.chunks_created
            accepted.append(entry)
        else:
            rejected.append(entry)

    job.accepted_files = accepted
    job.rejected_files = rejected
    job.status = "completed" if not rejected or accepted else "completed_with_errors"
    if not accepted and rejected:
        job.status = "failed"
    job.completed_at = datetime.utcnow()
    await db.commit()

    logger.info("ingestion_job_done", job_id=str(job.id), status=job.status,
                accepted=len(accepted), rejected=len(rejected))
    return job
