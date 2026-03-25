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

## Поисковый pipeline

1. Нормализовать запрос
2. Построить embedding запроса
3. Выполнить vector search c `top_k=8` по умолчанию
4. Удалить дубликаты / почти идентичные chunk
5. Ограничить контекст генерации до `max_chunks_in_prompt=4`
6. Вернуть top candidates и метаданные оценок

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

- По умолчанию `vector-only`
- Без отдельного reranker в PoC
- Без автоматического hybrid search
- Качество зависит от chunking и качества исходного текста

## Правило дедупликации

- два chunk считаются дубликатами для сборки промпта, если принадлежат одному документу, идут подряд и имеют значительное текстовое пересечение;
- в промпт предпочитается более релевантный из пары почти одинаковых chunk;
- метаданные о выброшенных дублях не теряются и могут быть записаны в отладочные логи.

## Ошибки

- `retrieval_timeout`
- `embedding_error`
- `storage_error`
- `empty_index`
