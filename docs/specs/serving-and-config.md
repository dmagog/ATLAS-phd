# Спецификация развертывания и конфигурации

## Форма развертывания

PoC разворачивается локально и состоит из:
- backend-приложения на `FastAPI`;
- `PostgreSQL + pgvector`;
- локального volume для загруженных файлов.

Telegram-адаптер не является обязательной частью основного пути развертывания и может быть включен после стабилизации web-first сценария.

## Конфигурация

Канонический список — `.env.example`. Сводка по категориям ниже.

### App
- `APP_ENV` — `development` (default) | `production`. В `production` валидаторы Settings требуют `JWT_SECRET ≥ 32` символов и `ADMIN_PASSWORD ≥ 12`, плюс активируется HSTS-заголовок.

### Аутентификация и админ
- `JWT_SECRET` — обязателен. Слабые placeholder-значения (`change_me_in_production`, `secret`, `password`, `admin`) отвергаются на старте.
- `ADMIN_EMAIL`, `ADMIN_PASSWORD` — bootstrap первого super-admin'а.

### LLM
- `LLM_API_KEY` — OpenRouter ключ. Placeholder `your_openrouter_key_here` отвергается.
- `LLM_MODEL_ID` — например `meta-llama/llama-3.3-70b-instruct:free`.
- `REQUEST_TIMEOUT_MS` — default 180000 (3 мин для reasoning-моделей).

### База
- `DATABASE_URL` — обязателен.
- `POSTGRES_PASSWORD` — обязателен в `.env` для `docker-compose` (без default-значения; раньше был `atlas_dev` — опасно для production).

### Multi-tenancy
- `PILOT_TENANT_SLUG` — какой тенант видит super-admin без `X-Atlas-Tenant` header'а (default `optics-kafedra` после миграции 0007).
- `VERIFIER_ENABLED` — A/B-тоггл M3.D (`true` — verifier hard-gate включён).

### Security middleware
- `TRUSTED_HOSTS` — CSV-список, default `*` (только для dev). В production обязательно: `atlas.example.com,www.atlas.example.com`.
- `CORS_ALLOWED_ORIGINS` — CSV-список origin'ов. Пусто (default) = same-origin only, безопасно для текущего Jinja2 UI. В production при отдельном фронтенде задать `https://atlas.example.com`.
- `HSTS_MAX_AGE` — default 31536000 (1 год, OWASP-рекомендация).

### Upload-лимиты (`/admin/ingestion-jobs`)
- `UPLOAD_MAX_FILE_SIZE_MB` — default 50. Превышение → 413.
- `UPLOAD_MAX_TOTAL_SIZE_MB` — default 200 (на job).
- `UPLOAD_MAX_FILES_PER_JOB` — default 50.

### Прочее
- `LOG_LEVEL` — default `INFO`.
- `EMBEDDINGS_URL` — default `http://localhost:8001`.
- `RETRIEVER_*` — параметры retriever'а (см. `src/atlas/core/config.py`).

## Секреты

- Секреты не коммитятся в репозиторий (`.env` в `.gitignore`).
- Используются только через `.env` / переменные окружения.
- Ротация секретов для PoC ручная.
- На старте `Settings` валидирует, что `JWT_SECRET`, `ADMIN_PASSWORD`, `LLM_API_KEY` не равны заведомо слабым placeholder'ам — приложение не запустится с дефолтным `.env.example`.
- В логах `email`, `password`, `jwt`, `api_key`, `authorization`, `cookie` маскируются автоматически (см. [docs/security.md §7](../security.md)).

## Версионирование

- Фиксируется версия schema/migrations.
- Фиксируются идентификаторы моделей генерации и embeddings.
- Изменения prompt/template policy должны версионироваться в коде.

## Запуск PoC

Базовый сценарий:
1. поднять PostgreSQL;
2. применить миграции;
3. поднять backend;
4. загрузить тестовый корпус;
5. прогнать smoke-сценарий через web UI.
