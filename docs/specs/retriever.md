# Спецификация retriever

## Назначение

`Retriever` поставляет релевантный подтверждающий контекст для `Q&A`.

## Источники

- одобренные учебные материалы, загруженные администратором;
- форматы: `pdf`, `docx`, `txt`, `md`.

## Индекс

- таблица документов;
- таблица метаданных chunk;
- векторное поле embeddings в `pgvector`.

Базовые параметры PoC:
- `chunk_size`: `800-1200` символов целевого текста;
- `chunk_overlap`: `100-200` символов;
- chunk сохраняет `document_id`, `document_title`, `section_or_page`, `chunk_order`, `text`, `embedding_version`.

## Поисковый pipeline (гибридный)

1. Нормализовать запрос
2. Построить embedding запроса
3. Выполнить **vector search** (pgvector cosine) с `top_k=8` по умолчанию
4. Выполнить **BM25 search** (PostgreSQL FTS `plainto_tsquery('simple', ...)`) с тем же `top_k`
5. Объединить списки через **Reciprocal Rank Fusion**:
   `rrf = 1/(k + rank_vector) + 1/(k + rank_bm25)`, где `k=60` (стандартный параметр)
6. Если BM25 не дал результатов (запрос вне словаря) — автоматический fallback на vector-only
7. Удалить дубликаты / почти идентичные chunk
8. Ограничить контекст генерации до `max_chunks_in_prompt=4`
9. Вернуть top candidates и метаданные оценок

Гибридный поиск особенно важен для текстов по оптике и физике,
где точные термины (названия эффектов, греческие символы) могут не иметь
близких embedding-соседей.

## Evidence gate (guardrails)

Retriever выставляет флаг `enough_evidence`, который проверяет `Verifier Node`:
- `top1_score >= 0.62`
- минимум 2 фрагмента с `score >= 0.55`

Пороги скалиброваны под модель `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, RU+EN).
Все параметры вынесены в конфиг (`retriever_min_top1_score`, `retriever_min_score_threshold`, `retriever_min_chunks_above_threshold`).

## Контракт

Вход:
- `query`
- `top_k`
- `filters` (optional)

Выход:
- `candidates[]`:
  - `chunk_id`
  - `document_id`
  - `document_title`
  - `section_or_page`
  - `text`
  - `score`
- `top1_score`
- `enough_evidence_hint`

## Ограничения

- Без отдельного cross-encoder reranker в PoC
- `plainto_tsquery('simple', ...)` без морфологии: не знает падежей и форм слов
- Качество зависит от chunking и качества исходного текста
- BM25 требует наличия `text_search_vec` колонки (миграция `0003`)

## Правило дедупликации

- два chunk считаются дубликатами для сборки промпта, если принадлежат одному документу, идут подряд и имеют значительное текстовое пересечение;
- в промпт предпочитается более релевантный из пары почти одинаковых chunk;
- метаданные о выброшенных дублях не теряются и могут быть записаны в отладочные логи.

## Ошибки

- `retrieval_timeout`
- `embedding_error`
- `storage_error`
- `empty_index`
