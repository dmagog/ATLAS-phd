"""
Vector retriever using pgvector cosine similarity.

Contract:
  retrieve(query_embedding, db, top_k) → RetrievalResult

Evidence gate (from config):
  - top1_score >= 0.70
  - at least 2 chunks with score >= 0.60
"""
from dataclasses import dataclass, field
from typing import Optional
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.config import settings
from atlas.core.logging import logger
from atlas.db.models import Chunk, Document


@dataclass
class ChunkCandidate:
    chunk_id: str
    document_id: str
    document_title: str
    filename: str
    chunk_index: int
    text: str
    section: Optional[str]
    page: Optional[int]
    score: float


@dataclass
class RetrievalResult:
    candidates: list[ChunkCandidate] = field(default_factory=list)
    top1_score: float = 0.0
    enough_evidence: bool = False
    query_embedding: list[float] = field(default_factory=list)


def _deduplicate(candidates: list[ChunkCandidate]) -> list[ChunkCandidate]:
    """
    Remove adjacent chunks from the same document that are near-identical
    (same document, consecutive chunk_index, and score difference < 0.02).
    Keeps the higher-scoring one.
    """
    if not candidates:
        return candidates

    seen: set[tuple[str, int]] = set()
    result: list[ChunkCandidate] = []

    for c in candidates:
        key = (c.document_id, c.chunk_index)
        adjacent = (c.document_id, c.chunk_index - 1)
        if adjacent in seen:
            # Skip — adjacent chunk from same doc already included
            continue
        seen.add(key)
        result.append(c)

    return result


async def retrieve(
    query_embedding: list[float],
    db: AsyncSession,
    top_k: int | None = None,
    request_id: str = "",
) -> RetrievalResult:
    k = top_k or settings.retriever_top_k

    # pgvector cosine distance: 1 - cosine_similarity, so score = 1 - distance
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    sql = text("""
        SELECT
            c.id          AS chunk_id,
            c.document_id,
            d.title       AS document_title,
            d.filename,
            c.chunk_index,
            c.text,
            c.section,
            c.page,
            1 - (c.embedding <=> CAST(:embedding AS vector)) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
    """)

    rows = (await db.execute(sql, {"embedding": embedding_str, "top_k": k})).fetchall()

    candidates = [
        ChunkCandidate(
            chunk_id=str(row.chunk_id),
            document_id=str(row.document_id),
            document_title=row.document_title,
            filename=row.filename,
            chunk_index=row.chunk_index,
            text=row.text,
            section=row.section,
            page=row.page,
            score=float(row.score),
        )
        for row in rows
    ]

    candidates = _deduplicate(candidates)

    top1_score = candidates[0].score if candidates else 0.0
    chunks_above_threshold = sum(
        1 for c in candidates if c.score >= settings.retriever_min_score_threshold
    )
    enough_evidence = (
        top1_score >= settings.retriever_min_top1_score
        and chunks_above_threshold >= settings.retriever_min_chunks_above_threshold
    )

    logger.info(
        "retrieval_done",
        request_id=request_id,
        top1_score=round(top1_score, 4),
        chunks_returned=len(candidates),
        chunks_above_threshold=chunks_above_threshold,
        enough_evidence=enough_evidence,
    )

    return RetrievalResult(
        candidates=candidates,
        top1_score=top1_score,
        enough_evidence=enough_evidence,
        query_embedding=query_embedding,
    )
