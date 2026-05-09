# Security — обзор защитных механизмов

Сводный документ по защитным средствам ATLAS-phd. Для каждой темы указан
источник истины (`.env.example`, конкретный модуль) — здесь только обзор.

История: средства внедрены в ходе security-audit'а, ветка `security-audit`,
2026-05-09. См. CHANGELOG.md v0.8.2 для полного списка изменений.

## 1. Аутентификация и сессии

| Механизм | Где | Параметры |
|----------|-----|-----------|
| Хеш паролей | [src/atlas/core/security.py](../src/atlas/core/security.py) | Argon2 (passlib) |
| JWT-сессии | [src/atlas/core/security.py](../src/atlas/core/security.py) | HS256, 8 часов, `jv` claim для отзыва |
| Constant-time login | [src/atlas/api/routers/auth.py](../src/atlas/api/routers/auth.py) | `burn_dummy_verify` для несуществующих/soft-deleted пользователей — нельзя различить «email есть, пароль не тот» от «email не существует» по таймингу |
| Хранение токена в браузере | [src/atlas/templates/login.html](../src/atlas/templates/login.html) | `localStorage` — **известная гэпа**, миграция на httpOnly cookie + CSRF в roadmap |

## 2. Rate limiting

In-memory лимиты (per-process). При scale-out на несколько workers
заменить на Redis-based limiter (TODO в `src/atlas/core/rate_limit.py`).

| Endpoint | Лимит | HTTP-ответ при превышении |
|----------|-------|--------------------------|
| `POST /auth/login` | 5/email + 50/IP за 5 мин | `429 Too Many Requests` + `Retry-After` |
| `POST /qa/message` | 60/час per-user | `429` + `Retry-After: 3600` |
| `POST /chat/message` | 60/час per-user | `429` |
| `POST /self-check/start` | 60/час per-user | `429` |
| `POST /self-check/{id}/submit` | 60/час per-user | `429` |

Super-admin исключён из LLM-квоты (eval/seed-скрипты ходят под ним
и должны делать сотни запросов).

## 3. Authorization & multi-tenancy

| Контроль | Где |
|----------|-----|
| RBAC: 4 роли (super_admin, tenant_admin, supervisor, student) | [src/atlas/core/deps.py](../src/atlas/core/deps.py) |
| Tenant-резолвер с явным reject cross-tenant header'а | [src/atlas/db/tenant_helpers.py](../src/atlas/db/tenant_helpers.py) |
| `assert_tenant_writable` для блокировки записей в read-only/archived tenant'е | [src/atlas/db/tenant_helpers.py](../src/atlas/db/tenant_helpers.py) |
| audit_log: append-only журнал критических действий | `audit_log` table, [src/atlas/db/audit.py](../src/atlas/db/audit.py) |

**IDOR-аудит** (security-audit, 2026-05-09): один critical-bug найден
и закрыт в `/self-check/{attempt_id}/submit` — fetch теперь фильтруется
по `tenant_id + user_id`, не только по UUID попытки.

## 4. Upload-ограничения (`/admin/ingestion-jobs`)

| Лимит | Default | env var |
|-------|---------|---------|
| Размер одного файла | 50 MB | `UPLOAD_MAX_FILE_SIZE_MB` |
| Суммарный размер job'а | 200 MB | `UPLOAD_MAX_TOTAL_SIZE_MB` |
| Файлов на один job | 50 | `UPLOAD_MAX_FILES_PER_JOB` |

Превышение → `413 Payload Too Large` с понятным сообщением.

**Path traversal**: `safe_filename()` отрезает `..`/абсолютные пути, плюс
проверка `resolve()` под `corpus_dir.resolve()` как defense in depth.
См. [src/atlas/ingestion/pipeline.py](../src/atlas/ingestion/pipeline.py).

## 5. Web hardening

Middleware регистрируется в [src/atlas/api/middleware.py](../src/atlas/api/middleware.py)
и подключается в `main.py:register_security_middleware`.

| Заголовок | Значение | Когда |
|-----------|----------|-------|
| `Content-Security-Policy` | `default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; ...` | всегда |
| `X-Frame-Options` | `DENY` | всегда |
| `X-Content-Type-Options` | `nosniff` | всегда |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | всегда |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=(), payment=()` | всегда |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | только при `APP_ENV=production` |

`TrustedHostMiddleware` подключается, если `TRUSTED_HOSTS != "*"`.
`CORSMiddleware` подключается, только если задан `CORS_ALLOWED_ORIGINS`
(пусто = same-origin only, безопасный default для текущего Jinja2 UI).

## 6. LLM-специфичные защиты

| Риск | Механизм | Где |
|------|----------|-----|
| Prompt injection из загруженного корпуса | Chunks в промпте обёрнуты в `<<<DOCUMENT idx=N ...>>> ... <<<END_DOCUMENT>>>` маркеры; system prompt инструктирует LLM воспринимать содержимое как данные | [src/atlas/qa/prompts.py](../src/atlas/qa/prompts.py) |
| Sanitization: атакующий не может «закрыть» wrapper изнутри | `<<<` → `‹‹‹`, `>>>` → `›››` в content | то же |
| Подделка `system`-сообщения через `conversation_history` | `HistoryMessage.role: Literal["user", "assistant"]` — Pydantic 422 на `"system"` | [src/atlas/api/routers/qa.py](../src/atlas/api/routers/qa.py), [chat.py](../src/atlas/api/routers/chat.py) |
| Verifier hard-gate — блокирует LLM-call при `enough_evidence=False` | M3.A.0 закрыл старую гэпу M2 | [src/atlas/orchestrator/qa_flow.py](../src/atlas/orchestrator/qa_flow.py) |

## 7. Логи и PII

`structlog`-процессор `_redact` в [src/atlas/core/logging.py](../src/atlas/core/logging.py)
ДО рендеринга маскирует:

- **email** (`email`, `*_email` ключи) → `a****@domain.com`
- **секреты** (`password`, `token`, `jwt`, `api_key`, `authorization`, `cookie`,
  `hashed_password`, `secret`, `client_secret`) → `***REDACTED***`

Это защита-в-глубину: даже если разработчик случайно положит
`logger.info('...', api_key=settings.llm_api_key)`, ключ не уйдёт в plaintext.

## 8. Конфигурация секретов (fail-fast)

[src/atlas/core/config.py](../src/atlas/core/config.py) валидирует на старте:

- `JWT_SECRET`, `ADMIN_PASSWORD`, `LLM_API_KEY` не равны заведомо слабым
  placeholder'ам из `.env.example` — иначе процесс не стартует.
- В `APP_ENV=production` дополнительно: `JWT_SECRET` ≥ 32 символов,
  `ADMIN_PASSWORD` ≥ 12 символов.

## 9. Контейнеры

| Сервис | User | Healthcheck |
|--------|------|-------------|
| `app` (production stage) | `atlas:10001` (non-root) | ✅ `/health` |
| `embeddings` | `emb:10002` (non-root) | ✅ `/health` |
| `postgres` | штатный postgres-юзер | официальный `pg_isready` |

Postgres и embeddings **не публикуют порты наружу** (внутренняя
docker-сеть). В dev для локального доступа `docker-compose.override.yml`
делает биндинг на `127.0.0.1`.

`POSTGRES_PASSWORD` обязателен в `.env` — без него `docker compose`
падает на старте (без default-значения `atlas_dev`).

## 10. Зависимости

- [.github/workflows/ci.yml](../.github/workflows/ci.yml): job `security-audit-deps`
  прогоняет `pip-audit` на каждый PR (`--strict` — любой known CVE
  блокирует merge).
- [.github/dependabot.yml](../.github/dependabot.yml): weekly-обновления
  pip / github-actions / docker. Security-апдейты выходят сразу при
  появлении advisory в GHSA.

## Production-чеклист

Перед публикацией ATLAS на сервере убедись:

- [ ] `.env` заполнен по `.env.example`, нет ни одного `REPLACE_WITH_*`
- [ ] `APP_ENV=production` (включает HSTS и строгие проверки секретов)
- [ ] `JWT_SECRET` ≥ 32 случайных символов (`python -c 'import secrets; print(secrets.token_urlsafe(48))'`)
- [ ] `ADMIN_PASSWORD` ≥ 12 символов
- [ ] `TRUSTED_HOSTS` указан явно (не `*`)
- [ ] Если фронтенд на отдельном домене — задан `CORS_ALLOWED_ORIGINS`
- [ ] Reverse-proxy с TLS (Caddy/nginx) перед `app:8731` —
      см. [docs/deployment/hetzner-setup.md](deployment/hetzner-setup.md)
- [ ] После настройки proxy: `docker-compose.yml` ports изменены на
      `127.0.0.1:8731:8731` (трафик только через proxy)
- [ ] `docker-compose.override.yml` в production не используется
      (это dev-only override)
- [ ] `pip-audit` зелёный (CI прогнал)

## Что осталось в roadmap

- **localStorage → httpOnly cookie + CSRF** (отдельный PR; ломает 30+ мест в шаблонах)
- **Redis-based rate-limiter** (для multi-worker деплоя)
- **Per-tenant LLM-квота** (страховка от «все студенты одного tenant'а вместе жгут лимиты»)
- **Жёсткий CSP без `unsafe-inline`** (требует переработки Jinja2-шаблонов с nonce'ами)
- **ZIP-bomb защита для DOCX/PDF** (monkey-patch `zipfile` или libmagic-проверка)
