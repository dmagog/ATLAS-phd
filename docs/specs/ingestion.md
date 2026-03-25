# Спецификация ingestion-контура

## Назначение

`Ingestion Pipeline` подготавливает учебные материалы к retrieval: валидирует файлы, извлекает текст, режет его на chunk и индексирует в `PostgreSQL + pgvector`.

## Поддерживаемые входы

- `pdf`
- `docx`
- `txt`
- `md`

Неподдерживаемые форматы отклоняются до запуска тяжелой обработки.

## Этапы pipeline

1. `accept`:
   - проверка MIME/extension;
   - расчет SHA-256;
   - присвоение `job_id` и `file_id`.
2. `extract`:
   - извлечение текста;
   - проверка, что текст непустой.
3. `normalize`:
   - очистка служебного мусора;
   - нормализация переносов и пробелов;
   - минимальная очистка подозрительных prompt-like паттернов в тексте.
4. `chunk`:
   - разбиение текста на chunk по правилам retriever spec.
5. `embed`:
   - batch generation embeddings.
6. `index`:
   - запись document metadata;
   - запись chunk metadata и embeddings;
   - фиксация итогового статуса файла.

## Статусы

Для файла:
- `accepted`
- `rejected`
- `processed`
- `failed`

Для job:
- `created`
- `running`
- `completed`
- `completed_with_errors`
- `failed`

## Идемпотентность

- повторная загрузка файла с тем же SHA-256 не должна создавать дубликаты chunk;
- повторный запуск `job` не должен дублировать уже успешно проиндексированные файлы.

## Ошибки

- `unsupported_format`
- `text_extraction_failed`
- `empty_document`
- `embedding_error`
- `index_write_error`

## Наблюдаемость

Логируются:
- `job_id`
- `file_id`
- `file_status`
- `duration_ms`
- `chunks_created`
- `error_code`
