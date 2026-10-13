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

Пороги — глобальные (settings.retriever_*), кафедра может переопределить их в
tenants.config.retrieval: {"min_top1_score", "min_score_threshold",
"min_chunks_above_threshold", "lexical_min_chunks"}.

Лексический путь (только если у кафедры задан lexical_min_chunks): если
векторный gate не прошёл, но значимые слова вопроса (без вопросительных и
служебных слов) ВСЕ встречаются хотя бы в lexical_min_chunks чанках —
evidence достаточно, а эти чанки добавляются в кандидаты. Сравнение — по
основам русского Snowball-стеммера PostgreSQL ('russian'), не по префиксам:
префикс «опер*» находил «операция», «фото*» — «фотография». Нужен
для терминов и аббревиатур (RACI, PDCA, «матрица Менделоу»), которые
MiniLM-эмбеддинг почти не различает (vscore 0.36–0.46 — ниже off-topic). Калибровка — scripts/calibrate_gate.py на
размеченном наборе (eval/gate_sets/), значения и замер — в CHANGELOG.
"""
from dataclasses import dataclass, field
from typing import Optional
import re
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from atlas.core.config import settings
from atlas.core.logging import logger
from atlas.db.models import Chunk, Document, Tenant


@dataclass(frozen=True)
class GateThresholds:
    min_top1_score: float
    min_score_threshold: float
    min_chunks_above_threshold: int
    lexical_min_chunks: int | None = None  # None — лексический путь выключен


# Вопросительные и служебные слова: в «Что такое матрица RACI?» значимы только
# «матрица» и «RACI» (стоп-лист 'russian' в PostgreSQL не убирает «такое»,
# «расскажи» и т.п.).
_STOPWORDS = frozenset("""
что такое такой такая такие кто как какой какая какие каков какова каковы чем чём
зачем почему где когда сколько ли это этот эта эти в во на и или а но по для о об от
до из у с со к ко при про за над под между без же бы не ни нет да его её их ее мне
мы вы он она они оно себя свой своя свои можно нужно надо есть быть был была было были
будет являются является расскажи объясни опишите опиши сформулируйте назовите перечислите
the a an of to in for and or what is are how why who which
""".split())
_WORD_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ]+")


def content_terms(query: str) -> list[str]:
    """Значимые слова запроса (для plainto_tsquery('russian', …): основы и
    оператор AND строит PostgreSQL)."""
    return [
        w for w in _WORD_RE.findall(query.lower())
        if w not in _STOPWORDS and len(w) >= 3
    ]


async def gate_thresholds(db: AsyncSession, tenant_id: uuid.UUID) -> GateThresholds:
    """Пороги evidence gate для кафедры: tenants.config.retrieval поверх settings."""
    config = (await db.execute(
        select(Tenant.config).where(Tenant.id == tenant_id)
    )).scalar_one_or_none() or {}
    cfg = config.get("retrieval") or {}
    return GateThresholds(
        min_top1_score=float(cfg.get("min_top1_score", settings.retriever_min_top1_score)),
        min_score_threshold=float(cfg.get("min_score_threshold", settings.retriever_min_score_threshold)),
        min_chunks_above_threshold=int(cfg.get(
            "min_chunks_above_threshold", settings.retriever_min_chunks_above_threshold
        )),
        lexical_min_chunks=(
            int(cfg["lexical_min_chunks"]) if cfg.get("lexical_min_chunks") else None
        ),
    )


_LEXICAL_SQL = text("""
SELECT
    c.id           AS chunk_id,
    c.document_id,
    d.title        AS document_title,
    d.filename,
    c.chunk_index,
    c.text,
    c.section,
    c.page,
    1 - (c.embedding <=> CAST(:embedding AS vector)) AS vscore,
    COUNT(*) OVER () AS total
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE c.tenant_id = :tenant_id
  AND d.status = 'active'
  AND to_tsvector('russian', c.text) @@ plainto_tsquery('russian', :tsquery)
ORDER BY ts_rank(to_tsvector('russian', c.text), plainto_tsquery('russian', :tsquery)) DESC
LIMIT :limit
""")

# Сколько лексически найденных чанков подмешивать в кандидаты (в промпт идут
# первые retriever_max_chunks_in_prompt).
_LEXICAL_CANDIDATES = 3


async def _lexical_evidence(
    db: AsyncSession, tenant_id: uuid.UUID, query_text: str, embedding_str: str
) -> tuple[int, list["ChunkCandidate"]]:
    terms = content_terms(query_text)
    if not terms:
        return 0, []
    rows = (await db.execute(_LEXICAL_SQL, {
        "tenant_id": tenant_id,
        "tsquery": " ".join(terms),
        "embedding": embedding_str,
        "limit": _LEXICAL_CANDIDATES,
    })).fetchall()
    total = int(rows[0].total) if rows else 0
    return total, [
        ChunkCandidate(
            chunk_id=str(r.chunk_id), document_id=str(r.document_id),
            document_title=r.document_title, filename=r.filename,
            chunk_index=r.chunk_index, text=r.text, section=r.section, page=r.page,
            score=float(r.vscore), vscore=float(r.vscore),
        )
        for r in rows
    ]


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
      AND c.tenant_id = :tenant_id
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
      AND c.tenant_id = :tenant_id
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
WHERE d.status = 'active'
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
  AND c.tenant_id = :tenant_id
  AND d.status = 'active'
ORDER BY c.embedding <=> CAST(:embedding AS vector)
LIMIT :top_k
""")


# ── Public interface ──────────────────────────────────────────────────────────

async def retrieve(
    query_embedding: list[float],
    db: AsyncSession,
    tenant_id: uuid.UUID,
    top_k: int | None = None,
    query_text: str | None = None,
    request_id: str = "",
) -> RetrievalResult:
    """
    Retrieve top_k chunks scoped to one tenant.

    M4.B: tenant_id is REQUIRED. Cross-tenant retrieval is forbidden by
    design (BDD 1.4, 8.2). Caller must resolve via
    `atlas.db.tenant_helpers.resolve_tenant_id_for_user`.

    If query_text is provided, runs hybrid (vector + BM25 via RRF).
    Otherwise runs vector-only search. Both filter chunks by
    `c.tenant_id = :tenant_id` and skip chunks belonging to documents
    with `status != 'active'` (superseded / deleted).
    """
    if tenant_id is None:
        raise ValueError("retrieve() requires tenant_id (M4.B tenant isolation)")

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
                        "tenant_id": tenant_id,
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
            # asyncpg marks the transaction as aborted after any error;
            # must rollback before executing another query.
            await db.rollback()
            use_hybrid = False
            mode = "vector_fallback"

    if not use_hybrid:
        rows = (
            await db.execute(
                _VECTOR_ONLY_SQL,
                {"embedding": embedding_str, "top_k": k, "tenant_id": tenant_id},
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
    gate = await gate_thresholds(db, tenant_id)
    top1_vscore = max((c.vscore for c in candidates), default=0.0)
    chunks_above_threshold = sum(
        1 for c in candidates if c.vscore >= gate.min_score_threshold
    )
    enough_evidence = (
        top1_vscore >= gate.min_top1_score
        and chunks_above_threshold >= gate.min_chunks_above_threshold
    )
    gate_path = "vector" if enough_evidence else None
    lexical_matches = None
    if not enough_evidence and gate.lexical_min_chunks and query_text:
        lexical_matches, lexical = await _lexical_evidence(db, tenant_id, query_text, embedding_str)
        if lexical_matches >= gate.lexical_min_chunks:
            enough_evidence = True
            gate_path = "lexical"
            seen = {c.chunk_id for c in lexical}
            candidates = (lexical + [c for c in candidates if c.chunk_id not in seen])[:k]

    logger.info(
        "retrieval_done",
        mode=mode,
        gate_path=gate_path,
        lexical_matches=lexical_matches,
        tenant_id=str(tenant_id),
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
