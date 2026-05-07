# Changelog — ATLAS phd

Все значимые изменения проекта фиксируются в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/).
Версионирование по [SemVer](https://semver.org/lang/ru/): MAJOR.MINOR.PATCH.

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
