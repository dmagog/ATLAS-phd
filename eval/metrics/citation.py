"""Citation accuracy через embedding similarity (M3.C).

Идея: процитированный фрагмент должен быть semantically близок к sentence из
ответа, который на него ссылается. Considered correct if cosine ≥ threshold,
threshold подбирается на калибровочной выборке.

NOTE: skeleton. Полная реализация требует:
1. Доступ к embedding service ATLAS (либо через публичный API, либо переиспользуя
   sentence-transformers модель локально).
2. Парсинг answer_text на sentence-units и matching с citation chunks.
3. Калибровка threshold на 30 ручно-размеченных примерах.

Эта инструментация — задача follow-up. Сейчас: skeleton с TODO маркерами.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CitationAccuracyResult:
    n_responses: int
    n_with_citations: int
    n_evaluated: int
    accuracy: float  # доля corretc citations; 0.0 если skeleton не активен


def citation_accuracy(
    responses: list[dict],
    entries_by_id: dict[str, dict],
    threshold: float = 0.65,
) -> CitationAccuracyResult:
    """SKELETON: возвращает заглушку до подключения embedding service.

    Корректная реализация (post-M3.B):
    1. Для каждой response с citations — экстракт sentence из answer_text, который
       аппелирует к данной citation (через positional reference или явный маркер).
    2. Embedding sentence + embedding citation chunk → cosine.
    3. Mark correct если cosine ≥ threshold.
    """
    n_with_citations = sum(1 for r in responses if r.get("citations"))
    return CitationAccuracyResult(
        n_responses=len(responses),
        n_with_citations=n_with_citations,
        n_evaluated=0,  # пока 0 — skeleton не активен
        accuracy=0.0,
    )
