"""
Hybrid retriever: vector (pgvector cosine) + BM25 (PostgreSQL FTS) via RRF.

Ranking strategy:
  - Vector search: top_k chunks by cosine similarity
  - BM25 search:   top_k chunks by ts_rank (PostgreSQL full-text search)
  - Merge:         Reciprocal Rank Fusion  rrf = 1/(k+rank_v) + 1/(k+rank_bm25)
                   where k = settings.retriever_hybrid_rrf_k (default 60)

When query_text is None or yields no BM25 matches, falls back to vector-only.

Evidence gate (Verifier input):
  top1_vscore  — cosine similarity of the best chunk after RRF reranking
  enough_evidence — top1_vscore >= min_top1_score
                    AND chunks_above_threshold >= min_chunks_above_threshold
"""
from dataclasses import dataclass, field
from typing import Optional
import uuid

from sqlalchemy import text
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
    score: float          # RRF score (used for ranking)
    vscore: float = 0.0  # raw cosine similarity (used for evidence gate)


@dataclass
class RetrievalResult:
    candidates: list[ChunkCandidate] = field(default_factory=list)
    top1_score: float = 0.0       # max vscore among candidates (for evidence gate)
    enough_evidence: bool = False
    query_embedding: list[float] = field(default_factory=list)


# ── Deduplication ─────────────────────────────────────────────────────────────

def _deduplicate(candidates: list[ChunkCandidate]) -> list[ChunkCandidate]:
    """
    Drop adjacent chunks from the same document that are nearly identical
    (same doc, consecutive chunk_index). Keeps the higher-scoring one.
    """
    if not candidates:
        return candidates

    seen: set[tuple[str, int]] = set()
    result: list[ChunkCandidate] = []

    for c in candidates:
        key = (c.document_id, c.chunk_index)
        adjacent = (c.document_id, c.chunk_index - 1)
        if adjacent in seen:
            continue
        seen.add(key)
        result.append(c)

    return result


# ── SQL helpers ───────────────────────────────────────────────────────────────

_HYBRID_SQL = text("""
WITH vector_ranked AS (
    SELECT
        c.id,
        ROW_NUMBER() OVER (ORDER BY c.embedding <=> CAST(:embedding AS vector)) AS vrank,
        1 - (c.embedding <=> CAST(:embedding AS vector))                        AS vscore
    FROM chunks c
    WHERE c.embedding IS NOT NULL
    ORDER BY c.embedding <=> CAST(:embedding AS vector)
    LIMIT :top_k
),
bm25_ranked AS (
    SELECT
        c.id,
        ROW_NUMBER() OVER (ORDER BY ts_rank(c.text_search_vec, query) DESC) AS brank
    FROM chunks c,
         plainto_tsquery('simple', :query_text) query
    WHERE c.text_search_vec IS NOT NULL
      AND c.text_search_vec @@ query
    ORDER BY ts_rank(c.text_search_vec, query) DESC
    LIMIT :top_k
),
merged AS (
    SELECT
        COALESCE(v.id, b.id)                                              AS id,
        COALESCE(1.0 / (:rrf_k + v.vrank), 0)
            + COALESCE(1.0 / (:rrf_k + b.brank), 0)                      AS rrf_score,
        COALESCE(v.vscore, 0.0)                                           AS vscore
    FROM vector_ranked v
    FULL OUTER JOIN bm25_ranked b ON v.id = b.id
)
SELECT
    m.id           AS chunk_id,
    m.rrf_score,
    m.vscore,
    c.document_id,
    d.title        AS document_title,
    d.filename,
    c.chunk_index,
    c.text,
    c.section,
    c.page
FROM merged m
JOIN chunks  c ON c.id = m.id
JOIN documents d ON d.id = c.document_id
ORDER BY m.rrf_score DESC
LIMIT :top_k
""")

_VECTOR_ONLY_SQL = text("""
SELECT
    c.id          AS chunk_id,
    c.document_id,
    d.title       AS document_title,
    d.filename,
    c.chunk_index,
    c.text,
    c.section,
    c.page,
    1 - (c.embedding <=> CAST(:embedding AS vector)) AS vscore
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE c.embedding IS NOT NULL
ORDER BY c.embedding <=> CAST(:embedding AS vector)
LIMIT :top_k
""")


# ── Public interface ──────────────────────────────────────────────────────────

async def retrieve(
    query_embedding: list[float],
    db: AsyncSession,
    top_k: int | None = None,
    query_text: str | None = None,
    request_id: str = "",
) -> RetrievalResult:
    """
    Retrieve top_k chunks.

    If query_text is provided, runs hybrid (vector + BM25 via RRF).
    Otherwise runs vector-only search.
    """
    k = top_k or settings.retriever_top_k
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
    rrf_k = settings.retriever_hybrid_rrf_k

    use_hybrid = bool(query_text and query_text.strip())
    mode = "hybrid" if use_hybrid else "vector"

    if use_hybrid:
        try:
            rows = (
                await db.execute(
                    _HYBRID_SQL,
                    {
                        "embedding": embedding_str,
                        "query_text": query_text,
                        "top_k": k,
                        "rrf_k": rrf_k,
                    },
                )
            ).fetchall()
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
                    score=float(row.rrf_score),
                    vscore=float(row.vscore),
                )
                for row in rows
            ]
        except Exception as exc:
            # BM25 failure (e.g. tsvector column missing before migration) → fall back
            logger.warning(
                "retrieval_hybrid_fallback",
                reason=str(exc),
                request_id=request_id,
            )
            use_hybrid = False
            mode = "vector_fallback"

    if not use_hybrid:
        rows = (
            await db.execute(
                _VECTOR_ONLY_SQL,
                {"embedding": embedding_str, "top_k": k},
            )
        ).fetchall()
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
                score=float(row.vscore),
                vscore=float(row.vscore),
            )
            for row in rows
        ]

    candidates = _deduplicate(candidates)

    # Evidence gate uses vscore (cosine similarity), not RRF score,
    # so thresholds remain calibrated to the embedding model.
    top1_vscore = max((c.vscore for c in candidates), default=0.0)
    chunks_above_threshold = sum(
        1 for c in candidates if c.vscore >= settings.retriever_min_score_threshold
    )
    enough_evidence = (
        top1_vscore >= settings.retriever_min_top1_score
        and chunks_above_threshold >= settings.retriever_min_chunks_above_threshold
    )

    logger.info(
        "retrieval_done",
        mode=mode,
        request_id=request_id,
        top1_vscore=round(top1_vscore, 4),
        chunks_returned=len(candidates),
        chunks_above_threshold=chunks_above_threshold,
        enough_evidence=enough_evidence,
    )

    return RetrievalResult(
        candidates=candidates,
        top1_score=top1_vscore,
        enough_evidence=enough_evidence,
        query_embedding=query_embedding,
    )
