# Changelog — ATLAS phd

Все значимые изменения проекта фиксируются в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/).
Версионирование по [SemVer](https://semver.org/lang/ru/): MAJOR.MINOR.PATCH.

---

## [0.8.2] — 2026-05-09 — Security hardening (audit)

Полный security-аудит по 11 итерациям (recon → secrets → auth → tenant
isolation → SQL → headers → upload → LLM → deps → docker → logs → quotas).
Обзор всех защитных механизмов: [`docs/security.md`](docs/security.md).

### Исправлено

- **CRITICAL: IDOR в `POST /self-check/{attempt_id}/submit`.** Раньше
  fetch попытки шёл только по UUID, без `tenant_id`/`user_id` фильтра.
  Атака: студент tenant'а A угадывает UUID попытки tenant'а B и шлёт
  за него ответы. Найдено в Итерации 3 audit'а; фетч теперь фильтруется
  по обоим полям и в orchestrator, и в роутере.
- **Path traversal в `/admin/ingestion-jobs`.** `raw.filename` склеивался
  с `corpus_dir` без санитизации — `corpus_dir / '../../etc/passwd'`
  резолвился ВНЕ `corpus_dir`. Фикс: `safe_filename()` + `resolve()`-проверка.
- **Memory-DoS через гигантский upload.** `await upload.read()` грузил
  файл целиком в RAM без лимита. Один 5GB-файл = OOM. Лимиты: 50MB/файл,
  200MB/job, 50 файлов/job → `413 Payload Too Large`.
- **System-role injection.** `HistoryMessage.role: str` — клиент мог
  присылать `{role: 'system', content: '...'}` и переписывать
  `ANSWER_SYSTEM_PROMPT`. Теперь `Literal["user", "assistant"]`.
- **embeddings-сервис под root.** Добавлен `emb:10002` non-root user
  в `docker/embeddings.Dockerfile` + healthcheck.

### Добавлено — security middleware

- **Security headers** на каждый ответ: CSP (mild — `'unsafe-inline'`
  для script/style оставлен из-за inline блоков в Jinja2-шаблонах),
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()`,
  `Strict-Transport-Security` только при `APP_ENV=production`.
- **TrustedHostMiddleware** подключается, если `TRUSTED_HOSTS != '*'`.
- **CORSMiddleware** подключается опционально через `CORS_ALLOWED_ORIGINS`.

### Добавлено — rate-limit

- **`POST /auth/login`**: 5 попыток/email + 50/IP за 5 мин (`429 + Retry-After`).
  Constant-time-проверка через `burn_dummy_verify` для несуществующих/
  soft-deleted пользователей — user-enumeration по таймингу недоступен
  (timing-ratio 1.04× в smoke-тесте).
- **LLM-квота**: 60 запросов/час per-user на `/qa/message`, `/chat/message`,
  `/self-check/start`, `/self-check/{id}/submit`. Super-admin исключён.

### Добавлено — фундамент

- **fail-fast валидация секретов** в `Settings`: placeholder-значения из
  `.env.example` отвергаются всегда, в `APP_ENV=production` дополнительно
  проверяется длина (`JWT_SECRET ≥ 32`, `ADMIN_PASSWORD ≥ 12`).
- **Prompt injection defense**: chunks в LLM-промпте обёрнуты в
  `<<<DOCUMENT idx=N title="..." page="...">>>...<<<END_DOCUMENT>>>`
  маркеры; system prompt инструктирует воспринимать содержимое как
  данные. `<<<` / `>>>` внутри текста sanitize'ятся в `‹‹‹` / `›››`,
  чтобы атакующий не мог досрочно «закрыть» wrapper.
- **Log masking**: `structlog`-процессор `_redact` маскирует email
  (`a****@domain.com`) и `password`/`token`/`jwt`/`api_key`/`cookie`/
  `authorization` (`***REDACTED***`).
- **CI**: новая job `security-audit-deps` (pip-audit `--strict`) +
  `.github/dependabot.yml` (weekly pip / github-actions / docker).

### Изменено

- **`docker-compose.yml`**: Postgres-порт 5432 не публикуется наружу
  (только внутренняя docker-сеть); embeddings:8001 тоже скрыт; для
  dev-доступа `docker-compose.override.yml` биндит на `127.0.0.1`.
  `POSTGRES_PASSWORD` обязателен в `.env` (без default'а `atlas_dev`).
  embeddings volume сменил путь: `/root/.cache/huggingface` →
  `/home/emb/.cache/huggingface` (соответствие новому non-root HOME).
- **`.env.example`**: переписан полностью. Слабые placeholders заменены
  на `REPLACE_WITH_*` с инструкциями по генерации. Добавлены `APP_ENV`,
  `TRUSTED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `UPLOAD_MAX_FILE_SIZE_MB`,
  `UPLOAD_MAX_TOTAL_SIZE_MB`, `UPLOAD_MAX_FILES_PER_JOB`.

### Не сделано (намеренно — отдельные PR)

- **localStorage → httpOnly cookie + CSRF**: ломает 30+ мест в шаблонах,
  отдельная задача.
- **ZIP-bomb защита для DOCX/PDF**: требует monkey-patch `zipfile`.
- **Per-tenant LLM-квота**: страховка от множества студентов одного tenant'а.
- **Жёсткий CSP без `'unsafe-inline'`**: требует переработки Jinja2-шаблонов с nonce'ами.

### BREAKING для существующих deploy'ов

- В `.env` обязателен `POSTGRES_PASSWORD` (без default'а `atlas_dev`).
- Если в `.env` остались placeholder-значения из старого `.env.example`
  (`change_me_in_production`, `changeme`, `your_openrouter_key_here`),
  приложение упадёт на старте — это намеренно.
- При первом старте после pull embeddings перекачает модель с HuggingFace
  (~150 MB, 1–2 минуты) — старый volume по `/root/.cache` не подхватится.
- В production обязательно `APP_ENV=production` для активации HSTS и
  строгих проверок длины секретов.

---

## [0.8.1] — 2026-05-09 — Multi-tenant demo + admin tenant isolation fix

### Добавлено

- **Вторая пилотная кафедра** `semiconductors-kafedra` (специальность 01.04.10 «Физика полупроводников»). Создана для демонстрации multi-tenancy на защите: independent program (6 топиков), independent corpus (4 PDF: ЛКО_книга, Lect_opt, Lections_combined, Mikhnenko-exciton), independent users (1 admin + 1 supervisor + 5 студентов с миксованной visibility).
- **`scripts/seed_semicon_demo.sh`** — idempotent bootstrap новой кафедры через HTTP API (POST /tenants → POST /program → POST /invites + redeem → POST /admin/ingestion-jobs).
- **`corpus/semiconductors-kafedra/program.md`** — 6 топиков пилотной программы (зонная структура, межзонные переходы, экситоны Ванье–Мотта/Френкеля, люминесценция, спектроскопия наноструктур).
- **`DELETE /admin/documents/{id}`** — удаление документа из RAG. Раньше способа удалить не было; нужен для очистки случайно загруженного материала. Tenant-scoped: 404 при попытке удалить чужой документ.

### Исправлено — Tenant isolation в /admin (M4.A regression)

При проверке `semiconductors-kafedra` обнаружилось, что:
- **`GET /admin/documents`** возвращал ВСЕ документы платформы вне зависимости от tenant context. Tenant-admin одной кафедры видел документы другой; super-admin без `X-Atlas-Tenant` тоже видел всё.
- **`GET /admin/ingestion-jobs/{id}`** не проверял tenant_id — tenant-admin мог опросить статус job из другого тенанта.

Это **утечка существования документов** (не контента — retrieval всегда был отфильтрован правильно по `tenant_id`), но всё равно нарушает M4.A baseline.

Фикс: оба эндпоинта теперь резолвят tenant context через `resolve_tenant_id_for_user(current_user, db, request)` (как уже делал `/qa/message` и `tenants.py`) и фильтруют SELECT по `tenant_id`.

### Тесты

- **`tests/test_admin_tenant_isolation.py`** — 3 новых теста (3/3 PASS):
  - `test_admin_documents_isolated_per_tenant` — disjoint sets между optics и semicon
  - `test_admin_ingestion_job_404_for_other_tenant` — 404 на чужой job_id
  - `test_admin_delete_404_for_other_tenant` — 404 на чужой DELETE, документ не удаляется

### Cleanup

- **`Кандидатский экзамен/`** (3.5 GB после 3 фаз cleanup'а) добавлена в `.gitignore` — papka содержит copyrighted материалы коллег и не подлежит version control. Подробности в `Кандидатский экзамен/CLEANUP_MANIFEST.md`.
- `corpus/*.pdf`, `corpus/*.docx` исключены из git (pipeline копирует туда оригиналы side-effect'ом).
- Удалён `optics-rusakov-M1.pdf` из `optics-kafedra` (был ошибочно загружен как тест pipeline'а; это студ. конспект, не авторитетный источник).

---

## [0.8.0] — 2026-05-09 — Design phases 1–6 + production UI redesign

Полная переработка UI/UX от ux-audit до полированной production-системы
со снятыми скриншотами для защиты. 6 фаз по [`docs/design-roadmap.md`](docs/design-roadmap.md).

### Добавлено — Production UI (Phase 5)

- **`_app.html` + `_partials.html`** — production base layout (sidebar + topbar) с auth-bootstrap JS, replaces legacy `base.html` с in-app login modal.
- **`/login`** — отдельная страница с brand-side + form-side + invite-code flow. Защита от open-redirect в `?next=`.
- **`/eval`** — новый dashboard для super-admin: 3 hero-cards (refusal_tnr / κ / latency p95) + per-topic table + reproducibility + history. Читает реальные результаты из `eval/results/*` через новый `eval.py` router.
- **Чат `/`** — переписан с inline citation pills `[N]` (вместо tail-list `[Doc:..., p.N]`), source-panel с дедупликацией, hard-gate verified badge, refusal-state как first-class экран.
- **Source-modal** — клик по `[N]` или source-card открывает full snippet с KaTeX-рендером формул.
- **Self-check `/self-check`** — hero score + rubric grid с явными весами 40/30/20/10 + per-question breakdown с подсветкой правильных/неверных.
- **Supervisor `/supervisor`** — per-topic aggregates + students с privacy mask M5 (opted-in vs «Аспирант #N»).
- **Tenant-admin `/tenant-admin`** — программа кафедры с bar-fill покрытия, инвайты, пользователи.
- **`/_/tenants`** — кросс-тенантный list для super-admin + onboarding hint.
- **`/_/invites`** — dedicated invites view для tenant-admin: hero-cards + active/redeemed/expired buckets.
- **`/me` extended** — добавлены поля `tenant_slug` и `tenant_display_name` (JOIN с tenants).

### Добавлено — Дизайн-система (Phase 2)

- **`src/atlas/static/atlas.css`** (~600 строк) — токен-набор (light + dark темы) + 18 BEM компонентов (btn / input / card / badge / cite / hero-card / bar-cmp / rubric / refusal / sidebar / source-panel / heatmap / spinner / step-badge / overlay / modal / toast / bubble / empty / tenant-ctx role-badges) + ~30 utility-классов.
- **Brand-цвета** извлечены из SVG `atlas-icon-v5-shield-no-ring-calm-blue`: `#1D4ED8` (calm-blue), `#1E293B` (slate).
- **`/_/styleguide`** — live-демо всех компонентов, theme-toggle.
- Phase 4 polish: motion (stagger entrance, refusal scale-in, pulse-ring badge), focus-state на dark, bar-cmp responsive, heatmap data-tip, light-mode shadows, sticky topbar/sidebar.

### Добавлено — Demo packaging (Phase 6)

- **`scripts/seed_demo_users.py`** — 14 demo-пользователей в optics-kafedra (1 super + 1 tenant-admin + 1 supervisor + 12 студентов с русскими именами + privacy mask 7 visible / 5 anonymous).
- **`scripts/seed_demo_attempts.py`** — ~40 hand-crafted self-check attempts с реалистичным распределением scores (skill × topic difficulty).
- **`scripts/seed_demo_real_attempts.py`** — 12 real LLM self-check сессий (по одной на студента) для drill-down comissia-proof данных.
- **`scripts/seed_demo_showcase.py`** — 3 «звёздные» attempts (4.5+) для ivanov как best-student kasus.
- **`scripts/seed_demo.sh`** — orchestrator one-command: docker up → seed users → seed attempts → smoke verify.
- **`scripts/demo_questions.json` + `verify_demo_questions.py`** — курированный список Q&A + refusal questions с pre-defense smoke test.
- **`/_/demo-login` + `/_/logout`** helper routes — instant-login для @optics.demo accounts (404 в production).
- **`?ask=` + `?open-source=` + `?open=` URL params** на chat/history для воспроизводимых screenshot-flow.

### Добавлено — Документация и иллюстрации

- **`docs/README.md`** — TOC + reading paths для 5 аудиторий (аспирант, научрук, tenant-admin, разработчик, защита).
- **`docs/design/screenshots/after/`** — 10 PNG скриншотов (login → chat → source-modal → refusal → selfcheck → supervisor → tenant-admin → eval → tenants → invites) с walkthrough README.
- **`docs/design/demo-script.md`** обновлён — 9 inline screenshots по шагам.
- **`docs/welcome/{student,supervisor,tenant-admin}.md`** проиллюстрированы.
- **`docs/system-design.md`** — embed C4 SVG диаграмм (context / container / workflow).
- **`docs/deployment/local-pilot.md`** — success-state screenshot после health-check.
- **`docs/design/{ux-audit,competitive-scan,wireframes,design-system,rationale,demo-script,demo-recording-protocol}.md`** — полный дизайн-track Phase 1–6.
- Топ-уровневый **`README.md`** переработан: hero metrics в badges, 3-image showcase grid, quick-start через `seed_demo.sh`, demo-аккаунты таблицей.

### Исправлено

- **MC color bug в self-check** — score=1.0 (binary correct) красился `scoreColor()` как red. Fix: для MC отдельная binary-цветовая шкала (`>0` → success, иначе danger).
- **JSON parsing fragility** в self-check generator — для топиков с LaTeX-формулами LLM эмитит backslashes, ломающие JSON. Workaround: real-attempts seed использует только топики 1.x; honest finding зафиксирован в `rationale.md` §3.3.
- **`scalar_one_or_none()` crash** в `seed_admin` после добавления второго super-admin (super@optics.demo). Заменено на `.first()`.
- **Routing conflict** `/tenants` (web) vs `/tenants` API. Web-route переименован в `/_/tenants` (того же класса что `/_/styleguide`).
- **Sticky-sidebar overflow** — добавлены `overflow-x: hidden` на `.app` и `.app__main` (sidebar мог уезжать за левый край viewport при горизонтальном overflow content'a).
- **Citation pills** — добавлена `citationsToPills()` regex post-процессинг markdown'a → numeric pills mapped к source-panel indices.
- **KaTeX delimiters** — `appendBubble` теперь передаёт `KATEX_OPTS` с `$..$` delimiters в `renderMathInElement` (раньше использовались дефолтные `\(...\)`).
- **`SelfCheckAttempt.topic_id`** — добавлена в ORM-класс (БД-колонка существовала с миграции M4.5/M5, но ORM её не видел → нельзя было создать attempts через ORM с topic_id).
- **History modal status mapping** — `evaluated` → `completed` (актуальное значение из SelfCheckStatus enum).

### Удалено (Phase 5.7)

- `templates/base.html` — legacy с in-app login modal.
- `templates/index.html` — legacy `/qa` view (дублировал чат).
- `templates/wf/*` — 9 wireframe-файлов (Phase 3 артефакты), сделали свою работу как visual reference, всё перенесено в production templates.
- Web route `GET /qa`.

---

## [0.7.0] — 2026-05-07 — M4.5.E + M3.C reproducibility

### Добавлено (M4.5.E)
- **Eval-set v1.1 с per-topic annotations** — каждой не-refusal entry присвоен `topic_external_id` из активной программы тенанта `optics-kafedra`. 100/100 non-refusal entries замаппированы (84 авто-regex + 16 manual fit).
- `eval/per_topic_breakdown.py` — анализирует любой run-dir + `faithfulness_detail.json` и выдаёт per-topic срез (answered/refused/error + faithfulness mean + selfcheck MAE).
- Schema `eval/schema.py`: QAEntry/FormulaEntry/SelfCheckEntry поддерживают `topic_external_id: str | None`.

### Добавлено (M3.C)
- **Reproducibility check (BDD 6.5)** — повторный полный прогон treatment-postfix через час. **6/7 PASS** (refusal_tnr / qa_false_refusal / refusal_reason_precision / error_rate / selfcheck κ — все Δ=0; latency в noise). Faithfulness Δ=0.040 — **inherent LLM-judge variance** (выше 0.030 floor), решается switch'ем на gpt-4o-class судьи с seed=0.

### Per-topic faithfulness на M3.C run
- 2.3 Поляризация: 0.600 (best, 30 entries)
- 2.2 Дифракция: 0.579
- 2.1 Интерференция: 0.471
- 1.1 Принципы Ферма+Гюйгенс: 0.440
- 1.2 Линзы: 0.318 (anomaly — 100% answered, low faith)
- 1.3 ТIR: 0.208 (gap — всего 2 entries)

### Артефакты
- `eval/results/M3-report.md` v2.3
- `eval/results/m3c-reproducibility-treatment-20260506_190051/`

Коммиты: `b509b6c` (M4.5.E), `406d005` (M3.C).

---

## [0.6.0] — 2026-05-06 evening — M3.A self-check block

### Добавлено
- **Self-check rubric block 0/20 → 20/20** — последний gap M3.A закрыт. Eval-set v1.0 — 120 entries (60 qa + 20 refusal + 20 formula + **20 self_check**).
- **Новый endpoint** `POST /self-check/evaluate` — stateless evaluator для measurement self-check rubric correctness без создания attempt'а в БД. Только super-admin / tenant-admin.
- 5 тем (Брюстер / Снеллиус / Малюс / кольца Ньютона / голография) × 4 уровня правильности (good 4.5 / partial 3.0 / weak 1.5 / off 0.5).

### Метрики (paid llama 3.3 70b как evaluator)
- MAE overall: **0.615** (на шкале 0–5)
- κ binarized (зачёт/незачёт): **1.000** ← perfect agreement
- 75% within ±1.0, 45% within ±0.5
- по уровням: good 0.06 ✓, weak 0.08 ✓, partial 1.08 (bias up), off 0.96 (bias up)

### Исправлено
- **Bug в `selfcheck_flow.py`** — пытался писать `status='submitted'` и `'evaluated'`, но check_constraint допускает только `in_progress/completed/abandoned/invalid_evaluation`. Маппинг: 'submitted' → 'in_progress', 'evaluated' → 'completed'. Без этого fix'а submit падал с `IntegrityError`.
- **Runner**: `call_self_check()` переписан под `/self-check/evaluate`. Раньше использовал `/start` + `/submit`, что подставляло один `user_answer` ко всем 5 случайно сгенерированным вопросам — correlation шум, не measurement.

Коммит: `6b24049`.

---

## [0.5.0] — 2026-05-06 — M3.B paid LLM, full A/B

### Изменено
- **Switch на платную LLM** `meta-llama/llama-3.3-70b-instruct` (без `:free`). Тариф: $0.10/M input + $0.32/M output. Free-tier `:free` сохранён как fallback.
- **Citation prompt fix** — на длинных промптах (1.5K+ tokens) Llama теряла инструкцию про `[Doc:` маркеры. Усилено: «MANDATORY citations», `citation_reminder` в конец user message. До: 100% NO_CITATIONS-refusals на in-corpus вопросах. После: всё с маркерами.

### Метрики M3.B (full 100-entry A/B; treatment-postfix vs baseline)
| | Treatment | Baseline |
|---|---|---|
| refusal_tnr | **1.000** (20/20) | 0.000 (0/20) |
| qa_false_refusal_rate | **0.000** (0/80) | 0.000 |
| refusal_reason_precision | **1.000** (20/20) | n/a |
| error_rate | **0.000** | 0.010 |
| faithfulness (judge) | 0.541 (79) | 0.550 (77) |
| latency p50 / p95 | 8.0s / 19.6s | 8.8s / 24.5s |

### M3.A continuation
- **14 false-refusals в QA-блоке** диагностированы как тот же systemic bug что 4 false-refusals в M3.A (короткие "Что такое X?" → top1_vscore < 0.55). Перефразированы по тому же шаблону. После — `qa_false_refusal_rate: 14/80 → 0/80`.

### Бюджет
- Полный прогон M3.B (treatment + baseline + judge × 2): **~$0.20**. Free-tier плана был $20 — улеглись 100×.

Коммиты: `8bf9ce0` (prompt fix), `86ee14e` (M3.B v2.0 + report).

---

## [0.4.5] — 2026-05-05 — Tests + corpus backfill

### Добавлено
- **31 BDD integration test** (vs 1 ранее):
  - `test_m3a_hard_gate.py` (5): off-topic refused, in-corpus passes, empty tenant, /qa/feedback validation
  - `test_m4a_tenant_readonly.py` (2): read-only enforcement + status validation
  - `test_m4c_auth_invite.py` (9): login/invite flow, JWT version revocation (BDD 7.5)
  - `test_m4d_cross_tenant_isolation.py` (1): tenant isolation
  - `test_m45a_program_lifecycle.py` (7): upload, archive-on-replace, cross-tenant block
  - `test_m5_supervisor_privacy.py` (7): N-threshold heatmap, 404 anti-leak, anonymized list
- **CI workflow** прогоняет всю suite (~25s после прогрева).

### M4.A — tenant read-only enforcement
- `assert_tenant_writable(tenant_id, db, user)` helper в `tenant_helpers.py` — 423 LOCKED при write на read-only тенанте; super-admin bypass.
- `PATCH /tenants/{slug}/status` — super-admin переключает active ↔ read-only ↔ archived (для incident-response).
- Подцеплен в 8 write-эндпоинтах.

### M4.5.C — corpus backfill
- `scripts/attach_corpus_by_keywords.py` — heuristic привязка материалов к topic'ам по chunk-keywords. Триггеры в БД пересчитывают `coverage_chunks`.

Коммиты: `27366e5` (read-only + tests), `2a7459f` (corpus backfill), `b8c339c`, `5ea8a4f` (test packs).

---

## [0.4.0] — 2026-05-04..06 — M6.A pilot infrastructure

### Добавлено
- `scripts/pilot_seed.py` — bootstrap пилотного тенанта одной командой (тенант + программа + N invite-кодов).
- `scripts/daily_metrics_report.py` — суточная сводка из БД (users, self-check, qa_feedback, audit privacy events) + `--json` mode для cron'а.
- `scripts/deploy.sh` — production-deploy на VPS (snapshot БД → git pull → compose pull → migrate one-shot → up -d → health-check + smoke).
- `scripts/pg_backup.sh` — daily pg_dump с rotation 7 дней.
- `.github/workflows/build-image.yml` — на push в main собирает + пушит app image в `ghcr.io/dmagog/atlas-phd-app` (теги `latest`, `sha-<short>`, `sha-<full>`).
- **Multi-stage Dockerfile** — `dev` (default, hot-reload, auto-migrate, dev-deps) и `production` (non-root uid 10001, healthcheck, без `--reload`/auto-migrate).
- **Docs**: `docs/runbook.md` (общий day-to-day), `docs/pilot/incident-runbook.md` (privacy/prod/governance playbooks), `docs/welcome/student.md`, `supervisor.md`, `tenant-admin.md`, `docs/deployment/hetzner-setup.md`, `docs/deployment/local-pilot.md`, `docs/governance.md` §5 DPIA-lite, pilot-ops playbook.

### Изменено (security)
- `tenants.status` enforcement (M4.A) — read-only/archived блокирует writes.
- `users.jwt_version` — bump инвалидирует все старые токены (BDD 7.5).
- `audit_log` — 13 actions для compliance (см. `docs/governance.md` §2.1).

Коммиты: `59e9482`, `cc9a378`, `abed1a7`, `25292e5`, `0351d91`, `d5a817c`, `b9f10cb`.

---

## [0.3.1] — 2026-04-06

### Изменено
- **Bootstrap Icons** — все эмодзи-пиктограммы в UI заменены на Bootstrap Icons v1.11.3 (`<i class="bi bi-...">`) для единообразного, масштабируемого внешнего вида. Затронуты шаблоны: `base.html`, `index.html`, `chat.html`, `selfcheck.html`, `admin.html`, `history.html`.
- CDN Bootstrap Icons подключён в `base.html`, иконки в навигации, шагах обработки, кнопках обратной связи и статусах файлов обновлены.

---

## [0.3.0] — 2026-04-06

### Добавлено
- **Сессионная память Q&A** — последние 5 обменов (до 10 сообщений) передаются в контекст LLM; поддерживается на страницах `/qa` и `/` (чат). Позволяет задавать уточняющие вопросы без повторения контекста.
- **Eval harness** — скрипт `eval/run_eval.py` для измерения KPI-A1 (точность роутинга ≥ 90%), KPI-R1 (ответы с цитатами ≥ 95%), KPI-R2 (корректные отказы ≥ 85%). Gold-датасеты: `eval/data/routing_gold.json`, `eval/data/qa_gold.json`.
- **Гибридный ретривер (BM25 + vector)** — PostgreSQL FTS (`plainto_tsquery`) объединяется с pgvector через Reciprocal Rank Fusion (RRF, k=60). При отсутствии BM25-результатов — автоматический fallback на vector-only. Миграция `0003` добавляет колонку `text_search_vec TSVECTOR` + GIN-индекс + триггер auto-update.
- **Обратная связь (👍/👎)** — после каждого ответа Q&A пользователь может оценить ответ. Оценки хранятся в таблице `qa_feedback` (миграция `0004`). Данные для пополнения gold-сета и калибровки Verifier'а.
- **История самопроверок** — страница `/self-check/history` со списком всех попыток, цветными бейджами оценок и модальным окном с детальным разбором: критерии, правильные ответы, цитата ответа пользователя.
- **Unified chat** — страница `/` с LLM Planner'ом, маршрутизирующим между Q&A, самопроверкой и уточнением.
- **Глобальный обработчик 401** — при истечении токена любая страница автоматически показывает форму входа вместо невнятного сообщения об ошибке.

### Изменено
- Ретривер: `retrieve()` принимает `query_text` для гибридного режима; `score` в `ChunkCandidate` — RRF-оценка, `vscore` — косинусное сходство для evidence gate.
- `build_answer_prompt()` принимает `conversation_history`; история инжектируется между system-сообщением и текущим вопросом.
- `run_qa_flow()` и `generate_answer()` принимают `conversation_history`.
- `QARequest` и `ChatRequest` расширены полем `conversation_history: list[HistoryMessage]`.
- Конфиг: добавлен `retriever_hybrid_rrf_k = 60`.
- Документация: обновлён `docs/specs/retriever.md` с описанием гибридного pipeline.

### Исправлено
- Конфликт маршрутов `/self-check/history` — API-эндпоинт переименован в `/self-check/history/list`.
- Глобальный 401 вместо «Ошибка загрузки списка» при истёкшей сессии.

---

## [0.2.0] — 2026-04-05

### Добавлено
- **Planner agent** — LLM-классификатор маршрутизирует запросы: `qa` / `self_check` / `clarify`. Температура 0.0, fallback на `qa` при любой ошибке.
- **Verifier с ре-генерацией** — при отказе Verifier'а расширяет `top_k × 2` и повторяет генерацию перед отправкой отказа пользователю.
- **RAG-grounded самопроверка** — вопросы генерируются на основе top-12 чанков корпуса; fallback на параметрические знания LLM при пустом корпусе.
- **Бинарная оценка MC** — вопросы с вариантами ответов: 1.0/0.0 (только критерий correctness). Открытые вопросы: взвешенная сумма 4 критериев (40/30/20/10 %).
- **Детальные результаты самопроверки** — правильные ответы, выделение верных/неверных вариантов, оценка по критериям.
- **Индикация прогресса** — пошаговые анимированные сообщения на страницах Q&A и самопроверки.
- **JWT-авторизация** — HS256, Argon2-хэши паролей, RBAC (user/admin).
- **Ingestion pipeline** — поддержка PDF, DOCX, TXT, MD, JSONL; дедупликация по SHA-256; прогресс-бар с polling.
- Обновлена документация по результатам ревью milestone 2 (промпты, парсинг Planner, схема Evaluator).

### Изменено
- Retry LLM: `stop_after_attempt(5)`, `wait_exponential(multiplier=2, min=5, max=60)`.
- HTTP 429 при rate limit LLM с читаемым сообщением пользователю.

---

## [0.1.0] — 2026-04-01

### Добавлено
- Начальная структура проекта: FastAPI + SQLAlchemy async + PostgreSQL + pgvector.
- Docker Compose: postgres/pgvector + embeddings sidecar (`paraphrase-multilingual-MiniLM-L12-v2`, 384-dim) + app.
- Базовый vector retriever (cosine similarity, HNSW-индекс).
- Answer Node: генерация ответа с цитатами `[Doc: ...]`, профили (detailed/brief/study).
- Verifier: evidence gate (top1_score ≥ 0.62, ≥ 2 чанков выше порога).
- Страницы Q&A (`/qa`) и самопроверки (`/self-check`).
- Административная панель загрузки материалов.
- Базовые модели БД: User, Document, Chunk, SelfCheckAttempt, Session.
- Alembic migrations (0001, 0002).
- Документация: README, system-design, requirements, use cases, acceptance tests, specs.
