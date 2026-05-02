# ATLAS phd: Roadmap эволюции после M2

> **Версия:** 0.17 (драфт)
> **Статус:** живой документ, прорабатывается итеративно
> **Контекст:** M2 (полный рабочий MVP) защищён. Этот план описывает развитие проекта от «учебного личного инструмента» к практически ценному продукту для одной кафедры. Публикационный трек явно вне scope.
> **Позиционирование:** ATLAS — **обучающая среда** для подготовки к кандэкзамену, не аттестационный сервис. Помогает учить, не оценивает формально. См. [bdd-scenarios.md §0](bdd-scenarios.md).

---

## 1. Контекст и точка отсчёта

### 1.1 Что уже есть (baseline после M2)

- Агентный контур над RAG: Retrieval → Answer → Verifier (hard-gate) → Self-check (Generator + Evaluator).
- Один корпус (оптика: Born&Wolf, Матвеев, Yariv), single-tenant.
- FastAPI + Jinja2 UI, Postgres+pgvector, локальные embeddings, OpenRouter LLM.
- RBAC: `user` / `admin`.
- Eval-set v0 запланирован в `product-proposal.md` §6.3 (120 элементов), но не превращён в reproducible eval-harness.
- Зоны роста, уже зафиксированные: hybrid retrieval (§7.2), 3-шаговый self-check с Feedback Agent (§7.6), персонализация (§7.5 — explicitly out of PoC).

### 1.2 Оценка прошлой защиты

| Ось | Балл | Что говорит рецензент |
|---|---|---|
| Актуальность | 6 | Нишевая боль, понятная аспирантам |
| Подход | 6 | Агентный цикл нетривиальнее простого чата |
| **Ценность** | **5** | «Как личный инструмент — самодостаточен. Нет бизнес-модели» |
| Реалистичность | 7 | Личная мотивация, технически несложно |

**Слабое место — ценность.** Потолок «личного инструмента» — это потолок «5». Чтобы пробить его, нужны реальные пользователи помимо автора и второй стейкхолдер с собственным интересом к системе (научрук/кафедра).

### 1.3 Стратегия следующих итераций

Одна ось: **кафедральный режим** — личный инструмент превращается в платформу для подготовки к кандэкзамену с видимостью для научрука. Это лечит «ценность 5» через появление второго стейкхолдера и реальных пользователей.

Eval-harness (M3) остаётся как **внутренний инструмент контроля качества** — нужен, чтобы перед заходом на реальных аспирантов знать, что система не деградировала после расширения корпуса и не врёт в новых разделах. Это не research-артефакт, а инженерная страховка перед пилотом.

Все артефакты публикационного трека (paper, arXiv, ВАК) — явно вне scope этого плана.

### 1.4 Платформенный принцип: «multi-направления by design, single-направление by ship»

Архитектурная установка: система — это **платформа** для произвольного количества направлений кандэкзамена (оптика, теоретическая физика, информатика и т. д.). Каждое направление — изолированный tenant со своей программой, корпусом, пользователями и научруком.

Но **в этом цикле отгружаем ровно одно направление — оптику**. Это:

- единственный реальный пилот;
- единственный наполненный корпус;
- единственный закрытый supervisor-флоу.

Что это даёт практически:

- В коде, схеме БД, API и UI tenant — first-class сущность с самого начала. Не «приклеиваем сбоку», когда захотим вторую кафедру.
- Все артефакты M4.5 (программа, реестр источников, eval-set v2) делаются в форме **переиспользуемого шаблона**: для второго направления это будет «заполнить такие же файлы по другой программе», а не «придумать процесс заново».
- Domain-specific промпты, концептные словари, частные эвристики не должны зашиваться в core — только в per-tenant конфиг.

Что это **не** даёт и НЕ обещает:

- Одновременной поддержки нескольких живых направлений в проде в этом цикле.
- Sharing корпуса между направлениями (cross-tenant retrieval — out-of-scope).
- Cross-domain faithfulness-метрик (для гуманитарных направлений правила другие — отдельный разговор).

---

## 2. Milestones

### M3 — Eval Harness (страховка качества перед пилотом)

**Длительность ориентировочно:** 2–3 недели

**Цель:** иметь воспроизводимый набор и runner, который позволяет в любой момент сказать «после такого-то изменения качество просело/выросло на X%». Это не для статьи — это чтобы при расширении корпуса до кафедральной программы (M4.5) и при первом контакте с аспирантами (M6) не выяснять качество эмпирически и больно.

**Scope (in):**
- Достроить eval-set v0 до полной разметки (60 Q&A + 20 refusal + 20 formula-heavy + 20 self-check, как описано в `product-proposal.md` §6.3) на текущем 3-учебниковом корпусе.
- Eval-runner: скрипт, прогоняющий весь набор через систему, логирующий ответы, цитаты, retrieval-traces, статусы графа, latency.
- Метрики:
  - **Faithfulness** — заявления ответа подтверждены процитированным фрагментом (LLM-judge; для внутренних целей достаточно одного прогона на сильной модели).
  - **Citation accuracy** — процитированные страницы реально содержат заявленный факт.
  - **Refusal correctness** — на off-topic/low-context набор система отказывает (true negative rate).
  - **Self-check rubric agreement** — оценка системы vs эталонная экспертная.
  - Latency p50/p95, error rate.
- **A/B сравнение** baseline (verifier off) vs treatment (полный контур) — это станет защитной цифрой для следующей защиты («агентный контур даёт +X% faithfulness»).
- Отчёт в `eval/results/M3-report.md`.

**Scope (out):**
- Hybrid retrieval — отложен в опциональный milestone «Hybrid retrieval» между M3 и M4.
- Методологическая строгость уровня публикации (двойная разметка, межрейтинговое согласие, ablations) — не нужна.

**Артефакты:**
- `eval/golden_set_v1/` — версионированный размеченный набор.
- `eval/runner.py` — скрипт прогона.
- `eval/results/` — JSON-логи + markdown-отчёт.
- Обновление `docs/specs/observability-and-evals.md`.

**Defense narrative:**
> «Перед тем как пускать аспирантов, мы измерили качество. На контрольном наборе из 120 элементов агентный контур даёт +X% faithfulness и −Y% галлюцинаций vs. plain RAG. Это наша страховка от регрессий при расширении корпуса.»

#### Подробный план M3

**M3.A — Eval-set v1: разметка golden set (≈1 неделя).**
Цель: 120 элементов, версионированы, лежат в `eval/golden_set_v1/` как JSONL.

Состав (по `product-proposal.md` §6.3):
- 60 Q&A — вопросы по реальному корпусу, на каждый есть эталонный ответ + список приемлемых страниц источников (одна или несколько комбинаций).
- 20 refusal — off-topic / out-of-corpus вопросы, на которые правильное поведение — отказ с понятной причиной (`low_relevance_top1`, `insufficient_evidence`).
- 20 formula-heavy — вопросы с формулами и плотной терминологией, где vector-only retrieval скорее всего проседает (вход для решения по опциональному milestone Hybrid retrieval).
- 20 self-check — открытые вопросы для генератора + эталонные оценки по рубрике (correctness/completeness/logic/terminology, шкала 0..5).

Шаблон записи (одна строка JSONL):
```json
{
  "id": "qa-001",
  "type": "qa",
  "tenant": "default",
  "query": "...",
  "expected_behavior": "answer",
  "acceptable_citations": [{"doc": "born-wolf", "pages": [123, 124]}],
  "reference_answer": "...",
  "tags": ["interference", "thin-films"],
  "difficulty": "medium",
  "version": "v1.0"
}
```
Для refusal: `expected_behavior: "refuse"`, `expected_refusal_reasons: ["low_relevance_top1"]`, `acceptable_citations: []`.

Процесс разметки:
1. Hand-craft базовых 30 элементов вручную как калибровка.
2. LLM-assisted draft оставшихся (генерируем кандидатов из чанков корпуса) → ручная валидация.
3. Adversarial и refusal блоки — ВСЕ вручную, без LLM (иначе систематический bias).
4. Версионирование: `golden_set_v1.0.jsonl` фиксируется и не меняется. Изменения = новая версия.

**M3.B — Runner (≈3–4 дня).**
Цель: `eval/runner.py` — CLI, который прогоняет golden set через систему и логирует всё нужное.

Контракт:
```
python eval/runner.py \
  --set eval/golden_set_v1.0.jsonl \
  --config eval/configs/treatment.yaml \
  --output eval/results/run-{timestamp}/
```
Выход: `responses.jsonl` (один ответ на запрос со всеми полями графа), `summary.json` (агрегированные метрики после M3.C), `trace/` (per-query retrieval traces для отладки).

Что логируется на каждый запрос: финальный ответ, список цитат, retrieval candidates (top-K + scores), статусы графа (`PLANNER_DECIDED → ... → RESPONSE_SENT/REFUSAL_SENT`), причина отказа если есть, latency по этапам, request_id, токены.

Архитектурное решение: runner ходит через **внутренний публичный API системы** (`/qa`, `/self-check`), не через внутренние модули. Это даёт более честную картину (включая сериализацию, auth, валидацию).

**M3.C — Метрики (≈3–4 дня, параллельно с M3.B).**

| Метрика | Определение | Реализация |
|---|---|---|
| Faithfulness | Доля заявлений в ответе, поддержанных процитированным фрагментом | LLM-judge: на каждый ответ + цитаты — промпт `проверь, поддерживается ли утверждение источником`, выход `[supported/not_supported]` per claim. Score = supported / total. |
| Citation accuracy | Доля цитат, которые реально содержат заявленный факт | Автоматически: проверяем, что embeddings цитированного фрагмента и соответствующего sentence в ответе достаточно близки. Threshold подбирается на калибровочной выборке. |
| Refusal correctness (refusal set) | TNR на 20 refusal-вопросах | `expected_behavior == actual_behavior` тривиально |
| Refusal correctness (Q&A set) | FNR на 60 Q&A | то же; ловим ложные отказы |
| Self-check rubric agreement | Совпадение оценок системы и эталона | MAE по 4 критериям + Cohen's kappa на binarized (≥3 / <3) |
| Latency p50/p95 | По логам runner | стандарт |
| Refusal reason precision | Когда отказали — по той ли причине? | Сравнение `refusal_reason` с `expected_refusal_reasons` |

LLM-judge модель: для M3 берём GPT-4-class (один прогон ≈ единицы $). Промпт judge — отдельный файл `eval/judge_prompts/faithfulness.md`, версионируется.

**M3.D — A/B протокол (≈1 день).**

Два конфига: `eval/configs/baseline.yaml` (`verifier.enabled: false`, `self_check.enabled: false` → plain retrieval+answer) vs `eval/configs/treatment.yaml` (полный контур).

Прогон: оба раза на одном и том же golden set, в один и тот же день (минимизация дрейфа стороны LLM-провайдера). Один и тот же `seed` где это применимо.

Результат: таблица метрик baseline / treatment / delta + интерпретация в отчёте.

**M3.E — Отчёт (≈1 день).**

Шаблон `eval/results/M3-report.md`: цели → методология (одна страница) → результаты (таблица baseline/treatment) → интерпретация (где агентный контур помог, где нет) → выводы для пилота → известные ограничения.

Сразу же вытаскиваем 3–5 «примеров красноречивых отказов» — это понадобится для defense-демо.

#### Чек-лист готовности M3

- [ ] `eval/golden_set_v1.0.jsonl` — 120 элементов, валидный JSONL, прошёл schema-проверку
- [ ] `eval/runner.py` — успешно прогоняет 5 пробных элементов
- [ ] Все 7 метрик имплементированы и протестированы на пробном run'е
- [ ] Конфиги baseline/treatment работают и дают разные траектории
- [ ] Полный прогон baseline + treatment занял < 2 ч и < $20 на API
- [ ] M3-report.md с цифрами зафиксирован
- [ ] BDD-сценарии 1.3, 6.1, 6.2, 6.3, 6.4, 6.5 — проходят (6 сценариев)

**Риски:**
- Free-tier LLM-judge может быть слабоват — на единичный прогон не критично перейти на платную модель (стоимость единицы долларов).
- Eval-set v0 рискует быть смещён к «удобным» вопросам → adversarial и formula-heavy блоки обязательны.
- При расширении корпуса в M4.5 потребуется eval-set v2 (новые разделы программы) — заложить в план M4.5.
- Citation accuracy через embedding-similarity threshold зависит от калибровки. Если калибровка неустойчива — fallback на ручную проверку 30% выборки.
- **Доступность free-tier модели меняется во времени.** Обнаружено в pre-M3 smoke (2026-05-01): `qwen/qwen3-8b:free` и `qwen/qwen3.6-plus:free` отсутствуют в OpenRouter-каталоге. Митигация: до старта M3 (M3.A.0) — `curl /api/v1/models`, выбрать рабочую free-модель из текущего списка (на 2026-05-02 рабочие: `meta-llama/llama-3.3-70b-instruct:free`, `nvidia/nemotron-3-super-120b-a12b:free`, `google/gemma-3-27b-it:free`). `LLM_MODEL_ID` фиксируется в `.env`/конфиге пилота на дату запуска.
- **M2 verifier hard-gate не блокирует flow на retrieval-уровне.** Обнаружено в pre-M3 smoke: при `enough_evidence=False` (top-K с relevance < threshold) ATLAS всё равно идёт в LLM-call; при ошибке LLM возвращается `api_status="error"` со статусом `TECHNICAL_ERROR`, а не `REFUSAL_SENT` (BDD 1.3). Это расхождение между текущей реализацией M2 и контрактом BDD. Митигация: M3.A.0 — починить verifier чтобы при `enough_evidence=False` возвращался hard-gate refusal без LLM-вызова; иначе метрика `refusal_correctness` (BDD 6.1) непредставима. Триггер: правится до first end-to-end run M3.B.

---

### Опциональный milestone — Hybrid retrieval (между M3 и M4)

> **Note:** название без M-номера сознательно — этот milestone отдельная опциональная вставка между M3 и M4, выполняется только при триггере.

**Длительность:** 1–2 недели
**Цель:** закрыть зону роста §7.2 продуктового документа. Показать на eval-harness, что hybrid retrieval даёт прирост на терминологических/формульных запросах.

**Триггер выполнения:** если в M3 видно, что vector-only проседает на formula-heavy блоке, или если eval-set v2 в M4.5.E показывает деградацию.

**Артефакт:** второе A/B в M3-отчёте (vector-only vs BM25+vector через RRF).

**Полезный побочный эффект:** для защиты — «у нас не только верификатор, но и сравнение retrieval-стратегий, обоснованное метриками».

---

### M4 — Multi-tenancy foundation

**Длительность:** 2–3 недели

**Цель:** разделить корпус, пользователей и сессии по тенантам, где **tenant = направление кандэкзамена** (см. §1.4). Без этого ось A не сдвигается, и платформенный принцип остаётся декларацией.

**Scope (in):**
- DB-схема: `tenant_id` в `users`, `materials`, `ingestion_jobs`, `qa_sessions`, `self_check_attempts`, `retrievals_log`.
- Новая сущность `tenants` (id, slug, display_name, created_at, owner_admin_id).
- Alembic-миграция: всё существующее → tenant `default` (потом переименуем/смержим в `optics-kafedra` на M4.5).
- Retrieval: фильтрация по `tenant_id` (composite index с HNSW; см. риски).
- Auth: привязка пользователя к tenant при регистрации; super-admin создаёт тенанты.
- UI: переключатель тенанта для super-admin; обычный пользователь видит только свой tenant.
- Изоляция: запросы пользователя tenant A никогда не достают chunks tenant B (тест на изоляцию обязателен; включить в CI).
- Per-tenant конфиг: namespace для тенанто-специфичных настроек (системные промпты, словари концептов — заглушка с дефолтами; реальное наполнение приходит в M4.5/M5).

**Scope (out):**
- Биллинг, квоты — не нужно для пилота.
- Cross-tenant поиск — out of scope by design.
- UI для самостоятельного создания тенантов пользователем — пока только super-admin.

**Артефакты:**
- Миграция + новый раздел в `docs/specs/web-and-api.md`.
- Тест на изоляцию данных в `tests/`.

**Defense narrative:**
> «От одного аспиранта — к одной кафедре. Технически: tenant_id-изоляция в retrieval, проверенная негативным тестом.»

#### Подробный план M4

**M4.A — Схема и миграция (≈5 дней).**

Новая таблица:

```sql
CREATE TABLE tenants (
  id UUID PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,           -- "optics-kafedra"
  display_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active', -- active | read-only | archived
  config JSONB NOT NULL DEFAULT '{}',  -- per-tenant config namespace
  created_at TIMESTAMPTZ NOT NULL,
  created_by UUID REFERENCES users(id)
);
```

Изменения существующих таблиц:
- `users` — добавить:
  - `tenant_id UUID REFERENCES tenants(id)` (NULL для super-admin)
  - `role TEXT NOT NULL` enum: `super-admin` / `tenant-admin` / `supervisor` / `student` (`tenant-admin` может быть несколько в одном тенанте)
  - `consent_recorded_at TIMESTAMPTZ` (BDD 4.10)
  - `deleted_at TIMESTAMPTZ` (soft-delete для BDD 7.3)
  - `jwt_version INT NOT NULL DEFAULT 1` (для инвалидации старых токенов после миграции и при role-revocation BDD 7.5)
- `materials` — добавить:
  - `tenant_id UUID NOT NULL REFERENCES tenants(id)`
  - `status TEXT NOT NULL DEFAULT 'active'` enum: `active` / `superseded` / `deleted` (BDD 4.13, 4.7); retrieval фильтрует только `active`
  - `superseded_by UUID REFERENCES materials(id)` (для версионирования)
  - `quality_score NUMERIC` (BDD 4.8) с флагом `low_quality BOOLEAN GENERATED`
- `ingestion_jobs`, `qa_sessions`, `self_check_attempts`, `retrievals_log` — `tenant_id UUID NOT NULL REFERENCES tenants(id)`.
- `self_check_attempts.user_id` — допустить NULL (анонимизация после удаления user'а — BDD 7.3).
- `chunks` — денормализованный `tenant_id` (избегаем JOIN'а на каждый retrieval; копируем из `materials`).

Новые таблицы (см. M4.C, M4.D): `invite_codes`, `audit_log`, `user_feedback`.

```sql
CREATE TABLE user_feedback (
  id BIGSERIAL PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  request_id TEXT NOT NULL,
  user_id UUID REFERENCES users(id),  -- nullable после soft-delete user'а
  rating TEXT NOT NULL,                -- enum: "incorrect" (зарезервировано на расширение)
  comment TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_at TIMESTAMPTZ,
  reviewed_by UUID REFERENCES users(id)
);
```

Миграция:
1. Создать `tenants` и `default` тенант (`slug='default'`).
2. Все существующие `materials`/`sessions`/`attempts` → `tenant_id = default.id`.
3. Существующий admin (M2 ENV-bootstrap) → `role = 'super-admin'`, `tenant_id = NULL`.
4. Не-admin users (если есть) → `role = 'student'`, `tenant_id = default.id`.
5. На старте M4.5 — explicit handoff: первое действие M4.5 = `UPDATE tenants SET slug='optics-kafedra', display_name='Кафедра оптики' WHERE slug='default'`. Дальше M4.5 загружает программу и расширяет корпус в этот же tenant. Альтернатива (создать новый tenant и перенести материалы) более чистая, но дороже — отвергнута для пилота.

Чек миграции на rollback: до миграции снимаем БД-дамп. После — smoke-тест retrieval работает на текущем корпусе.

**M4.B — Retrieval с tenant-фильтром и HNSW-стратегия (≈3 дня).**

Каждый query на `chunks` — обязательное `WHERE tenant_id = :current_tenant`. Это инвариант, заложенный в repository-слой (а не в каждый call site).

Стратегия индекса:
- Композитный HNSW-индекс с tenant-фильтром в pgvector не работает «из коробки» — фильтрация происходит post-search. На больших корпусах это даст просадку recall.
- Решение: **partial indexes per tenant** — `CREATE INDEX chunks_hnsw_optics ON chunks USING hnsw (embedding vector_cosine_ops) WHERE tenant_id = '...'::uuid;`.
- Цена: на каждый новый тенант нужно создавать отдельный индекс. Делается в `tenant.create()` хуке.
- На пилоте 1 тенант × ~10K-50K чанков: один HNSW-индекс полностью укладывается в M1 8GB.

Бенчмарк: до и после миграции прогнать retrieval на 50 запросах из golden_set_v1; убедиться, что recall не упал > 0.05 и latency p95 не вырос > 20%.

**M4.C — Auth, RBAC matrix, invite-flow (≈5 дней).**

JWT-payload расширяется: `{ user_id, tenant_id, role }`. `tenant_id` — `null` для super-admin (он cross-tenant).

RBAC matrix (как middleware-таблица):

| Действие | super-admin | tenant-admin | supervisor | student |
|---|---|---|---|---|
| Создать тенант | ✓ | — | — | — |
| Список всех тенантов | ✓ | — | — | — |
| Список пользователей тенанта | ✓ | свой | — | — |
| Загрузить/удалить material | ✓ | свой | — | — |
| Загрузить программу | ✓ | свой | — | — |
| Создать invite | ✓ | свой | — | — |
| Q&A / Self-check | — | свой (как пользователь) | свой | свой |
| Heatmap группы | — | свой | свой | — |
| Карточка аспиранта (opt-in) | — | — | свой при opt-in | только своя |
| Audit log тенанта | ✓ | свой | — | — |
| Audit log платформы | ✓ | — | — | — |

Принудительный фильтр по `tenant_id` для всех ролей кроме super-admin делается в декораторе/middleware, не на уровне views — это зеркалит инвариант M4.B.

Invite-flow:

```sql
CREATE TABLE invite_codes (
  code TEXT PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id),
  role TEXT NOT NULL CHECK (role IN ('tenant-admin', 'supervisor', 'student')),
  created_by UUID REFERENCES users(id),
  expires_at TIMESTAMPTZ,
  redeemed_at TIMESTAMPTZ,
  redeemed_by UUID REFERENCES users(id)
);
```

Срок действия — 7 дней. Redemption — единоразовый, при попытке повторного использования возвращается 410 Gone. Закрывает BDD 4.6, 4.10.

Bootstrap super-admin (BDD 4.9):
- При старте сервиса проверяется наличие user с `role='super-admin'`.
- Если нет — создаётся из ENV `ADMIN_EMAIL` + `ADMIN_PASSWORD` (Argon2).
- Если есть — ENV игнорируется (никаких silent overrides).

Tenant status transitions (BDD 8.3):
- `active` (default) → `read-only` — только super-admin; пользователи могут читать (Q&A, self-check), но запись (новые attempts, ingestion) блокируется. Применение через middleware-проверку перед write-операциями.
- `read-only` → `active` — только super-admin.
- `archived` (полная деактивация) — out-of-scope текущего цикла, схемой поддержано.

Role revocation (BDD 7.5):
- При отзыве роли инкрементится `users.jwt_version`. Старые токены с прежним `jwt_version` не валидны.
- Проверка `jwt_version` — на каждом запросе в auth-middleware.
- Запись в audit_log: `action='user.role.revoke'`, `target_id=user.id`, `details={old_role, new_role, by_actor}`.

Consent text (BDD 4.10):
- Текст политики обработки данных лежит как статическая markdown-страница в репозитории (`docs/consent.md`), рендерится в UI consent-блока.
- Версия политики (`consent_version` константа в коде) сохраняется в `users.consent_recorded_at` через композитное поле `consent_recorded_at_v{N}` либо отдельной таблицей `user_consents` (для аудита изменений политики). Для пилота достаточно одной версии — выбираем простой вариант с одним полем.

**M4.D — Audit log + integration-тест изоляции (≈3 дня).**

Audit log:

```sql
CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_id UUID,
  actor_role TEXT,
  tenant_id UUID,                -- null для платформенных событий
  action TEXT NOT NULL,          -- "tenant.create", "user.role.grant", "personal_data.access", ...
  target_type TEXT,
  target_id TEXT,
  request_id TEXT,
  details JSONB
);
```

Запись из middleware на критических действиях (см. BDD 7.1). UI чтения — стр. «Журнал событий» в админке tenant-admin (BDD 7.6) и cross-tenant у super-admin.

Integration-тест cross-tenant изоляции (BDD 8.2):
1. Сетап: 2 тенанта `t1`, `t2`, у каждого по 5 материалов с непересекающимся содержанием.
2. От лица аспиранта `t1` прогоняется 50 разных запросов через публичный API `/qa`.
3. Проверка: ни один retrieval candidate в логах не имеет `tenant_id = t2`.
4. Дополнительно: попытка прямого запроса `GET /api/materials/{material_id_из_t2}` от лица `t1` → 404 (не 403, чтобы не палить существование).
5. Тест включается в CI на каждый PR. Провал = блокировка merge.

**Сквозная задача — API surface (распределена между M4.A–M4.D).**

Не отдельная фаза, но фиксируем поверхность изменений, чтобы видеть полный объём:

- **Tenant management** (super-admin): `POST /api/tenants`, `GET /api/tenants`, `PATCH /api/tenants/{id}` (status), `GET /api/tenants/{id}/export` (BDD 7.2 — асинхронный экспорт через background job, manifest.json + .tar.gz).
- **User management** (tenant-admin своего тенанта, super-admin везде): `GET /api/tenants/{id}/users`, `PATCH /api/users/{id}` (role/deactivate), `DELETE /api/users/{id}` (soft-delete + анонимизация attempts).
- **Invite management**: `POST /api/invites`, `GET /api/invites` (свой tenant), `POST /api/invites/{code}/redeem`.
- **User feedback**: `POST /api/feedback` (BDD 1.8), `GET /api/feedback?tenant_id=...` (для tenant-admin).
- **Audit log**: `GET /api/audit?tenant_id=...&actor=...&action=...&from=...&to=...` (BDD 7.6) с пагинацией и CSV-экспортом.
- **Material lifecycle**: `POST /api/materials`, `DELETE /api/materials/{id}` (soft → status='deleted'), `POST /api/materials/{id}/replace` (для BDD 4.13 — старый superseded, новый active).

Email-уведомления (BDD 7.3 «email-подтверждение удаления»):
- Решение: для пилота — лог-стратегия. Письмо формируется и пишется в `outbound_emails` table со статусом `queued`. Реальная отправка через SMTP — out-of-scope M4 (можно прикрутить заглушку Mailtrap или скопировать из лога вручную).
- Это сохраняет интерфейс на будущее, но не блокирует пилот SMTP-инфраструктурой.

#### Чек-лист готовности M4

- [ ] Миграция применена; rollback-дамп зафиксирован
- [ ] Все existing данные в тенанте `default`; existing admin = super-admin; tenant_id-фильтр работает
- [ ] Partial HNSW-индекс создан, retrieval-бенчмарк не показывает деградации > порогов
- [ ] JWT включает tenant_id, role, jwt_version; RBAC-middleware покрывает все роуты
- [ ] Invite-flow работает end-to-end для всех 3 ролей (student, supervisor, tenant-admin)
- [ ] Consent-блок обязателен при регистрации; `users.consent_recorded_at` заполняется
- [ ] Bootstrap super-admin — проверен на чистой БД и на повторном запуске (idempotent)
- [ ] Role revocation инкрементит jwt_version; старые токены отклоняются
- [ ] Tenant status `active` ↔ `read-only` — переход работает, write-операции блокируются в read-only
- [ ] Schema для material-lifecycle готова (`status`, `superseded_by`, `quality_score`); operational сценарий 4.13 валидируется в M4.5 при наполнении корпуса
- [ ] User soft-delete + анонимизация attempts (user_id → NULL) работают
- [ ] User feedback: API + видимость в админке tenant-admin своего тенанта
- [ ] audit_log пишется на 6 ключевых действиях (BDD 7.1) + role-revocation
- [ ] Integration-тест cross-tenant изоляции зелёный в CI
- [ ] BDD-сценарии 1.1, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 4.1, 4.6, 4.9, 4.10, 4.11, 4.12, 7.1, 7.2, 7.3, 7.5, 7.6, 8.1, 8.2, 8.3 — проходят (21 сценарий)

**Риски:**
- **Partial indexes scaling.** На 10+ тенантов это станет неудобно (каждый — отдельный индекс). Митигация: пилот = 1 тенант, для масштабирования post-M6 переход на pgvector с filtered HNSW (если зарелизят) или sharding.
- **Rollback миграции на проде.** Если миграция упала на половине — chunks могут оказаться без tenant_id. Митигация: миграция в одной транзакции; перед миграцией — обязательный дамп; smoke-тест retrieval после.
- **Bootstrap idempotency.** Случайный второй запуск с другим ADMIN_PASSWORD не должен молча перезаписать пароль (BDD 4.9). Митигация: явный exit с информативным сообщением, если super-admin уже есть.
- **JWT и cache.** Старые токены до миграции не содержат tenant_id. Митигация: bump `jwt_version` в схеме user; старые токены инвалидируются при первой попытке использования.
- **Soft-delete user'а с активными attempts.** При удалении user'а его attempts остаются с `user_id=NULL`, но supervisor-аналитика (heatmap) должна корректно их учитывать. Митигация: явный test-кейс на heatmap с anonymized attempts.
- **Email-инфраструктура.** Без SMTP уведомления только в `outbound_emails` table. Это допустимо для пилота, но при росте — блокер. Митигация: явный TODO в M6 (если кафедра потребует реальные emails — переключить на SMTP-провайдер за 1 день).

---

### M4.5 — Корпус первого направления (оптика)

**Длительность:** 2–4 недели (значительная часть — не инженерная)

**Цель:** расширить корпус с 3 учебников (Born&Wolf, Матвеев, Yariv) до полной программы кандидатского минимума по оптике одной кафедры. Это первый реальный tenant и одновременно **референс-имплементация процесса**, который потом тиражируется на любое следующее направление (см. §1.4): «есть программа → разметили источники → загрузили → проверили покрытие → расширили eval-set».

**Scope (in):**
- **Программа кандэкзамена.** Получить от кафедры (или из открытых источников ВАК + адаптации кафедры) формализованный список тем/билетов кандэкзамена по оптике. Завести его как структурированный документ (`corpus/optics-kafedra/program.md`): разделы → темы → ключевые концепты.
- **Источники.** Под каждую тему программы — список рекомендованных источников (учебники, монографии, курсовые лекции кафедры, обзорные статьи). Часть уже есть (Born&Wolf, Матвеев, Yariv) — закрывает классическую и часть прикладной оптики; нужно докрыть пробелы (например, лазерная оптика, нелинейная, квантовая — в зависимости от профиля кафедры).
- **Ingestion + topic metadata.** При загрузке каждого материала проставлять привязку к разделам программы. Это даст retrieval с фильтром «искать только в материалах темы X», что повышает precision и закрывает offline-сценарий «аспирант готовится к билету N».
- **Coverage check.** Прогнать по программе автоматический контроль: для каждой темы есть ≥ K независимых релевантных фрагментов в индексе. Темы без покрытия — явный TODO для кафедры (доложить материалы).
- **Eval-set v2.** Расширить golden-set из M3: добавить 30–50 вопросов по новым разделам программы (как минимум по одному вопросу на тему программы). Прогнать M3-runner на новом корпусе — получить обновлённые метрики.

**Scope (out):**
- Не делаем мульти-кафедральные программы — одна кафедра, одна программа.
- Не делаем автоматическую сверку с обновлениями ВАК — программа фиксируется на дату пилота.
- Авторские права: используем то, что разрешено для учебных целей внутри кафедры; не публикуем сам корпус наружу.

**Артефакты:**
- `corpus/optics-kafedra/program.md` — структурированная программа.
- `corpus/optics-kafedra/sources.md` — реестр источников с привязкой к темам.
- Загруженный корпус в БД tenant `optics-kafedra` (после M4).
- `eval/golden_set_v2/` — расширенный набор.
- Coverage-report: какие темы покрыты, какие нет.

**Defense narrative:**
> «От 3 учебников и одного аспиранта — к полной программе кандэкзамена кафедры с topic-aware retrieval. Аспирант готовится по билету — система ищет в материалах именно этого билета, а не во всём корпусе.»

#### Подробный план M4.5

**M4.5.A — Формализация программы кандэкзамена (≈3–5 дней, преимущественно не инженерная).**

Артефакт: `corpus/optics-kafedra/program.md` — единый документ с фиксированной markdown-структурой:

```markdown
---
program_version: "v1.0"
tenant_slug: "optics-kafedra"
ratified_at: "2026-XX-XX"
---

## Раздел 1. Геометрическая оптика

### 1.1 Принципы Ферма и Гюйгенса
**key_concepts:** принцип Ферма, принцип Гюйгенса, эйконал

### 1.2 Тонкие линзы
**key_concepts:** уравнение тонкой линзы, главные плоскости

## Раздел 2. Волновая оптика

### 2.1 Интерференция
**key_concepts:** когерентность, интерферометр Майкельсона
...
```

Конвенция:
- `H2` = раздел программы.
- `H3` = билет (topic). Номер билета (`1.1`, `2.3`) = `external_id`, стабильный человекочитаемый идентификатор.
- `**key_concepts:**` — список ключевых концептов через запятую (используется в self-check generator и для defense-демо, не для concept-tagging — тот off scope).

Парсер (`scripts/load_program.py`) — markdown→DB, **atomic** загрузка (одна транзакция; либо вся программа в БД, либо ничего). Строгая schema-валидация: при расхождении — отказ с понятной ошибкой и точкой остановки.

**Ограничение схемы:** одноуровневые разделы (H2 → H3 → билеты). Многоуровневая структура (раздел → подраздел → билеты) для пилотной программы кандэкзамена не нужна; при возникновении — расширение через таблицу `program_sections` post-pilot.

**Параллельный артефакт `corpus/optics-kafedra/sources.md`** — реестр источников с привязкой к топикам в markdown-форме. Это **ручной reference-документ** для tenant-admin'а (что куплено, что общедоступно, какие разрешения), системой не парсится. Назначение: версионирование решений по copyright и удобство передачи кафедральному методисту.

Источник программы:
- Если у кафедры есть формализованный документ — оцифровать вручную.
- Если только устные традиции и список билетов на бумаге — собрать с научруком/завкафедрой за 1–2 встречи.
- Открытые источники ВАК как baseline (паспорт специальности), адаптация — кафедральная.

**M4.5.B — Schema для programs/topics/mappings (≈2 дня).**

Это новые таблицы, добавляются миграцией внутри M4.5 (не в M4 — там был только tenant-уровень).

```sql
CREATE TABLE programs (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  version TEXT NOT NULL,                  -- "v1.0"
  status TEXT NOT NULL DEFAULT 'active',  -- active | archived
  source_doc TEXT,                        -- путь к program.md в репо
  loaded_at TIMESTAMPTZ NOT NULL,
  loaded_by UUID REFERENCES users(id)
);
-- Только одна активная программа на тенант:
CREATE UNIQUE INDEX programs_one_active
  ON programs (tenant_id) WHERE status='active';

CREATE TABLE program_topics (
  id UUID PRIMARY KEY,
  program_id UUID NOT NULL REFERENCES programs(id),
  external_id TEXT NOT NULL,              -- "1.3" из markdown
  section TEXT NOT NULL,                  -- "Геометрическая оптика"
  title TEXT NOT NULL,                    -- "Тонкие линзы"
  ordinal INT NOT NULL,
  key_concepts TEXT[],
  UNIQUE (program_id, external_id)
);

CREATE TABLE material_topics (
  material_id UUID NOT NULL REFERENCES materials(id),
  topic_id UUID NOT NULL REFERENCES program_topics(id),
  PRIMARY KEY (material_id, topic_id)
);

CREATE TABLE chunk_topics (
  chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  topic_id UUID NOT NULL REFERENCES program_topics(id) ON DELETE RESTRICT,
  PRIMARY KEY (chunk_id, topic_id)
);
```

`ON DELETE` policy:
- `chunks` удаление каскадирует на `chunk_topics` (chunk нет → ссылок не нужно).
- `program_topics` НЕ удаляются (RESTRICT) — даже у archived программ остаются как immutable history; ссылки из existing attempts должны разрешаться. Программы и их topics — append+archive, не delete.
- `self_check_attempts.topic_id` FK на `program_topics(id)` ON DELETE RESTRICT — то же.
- `material_topics`: chunks_topics триггерится на **INSERT, UPDATE и DELETE** material_topics (не только INSERT). При переразметке материала чанки получают новые теги, старые удаляются.

Связи material→topics проставляются при ingestion (M4.5.C). chunks→topics — **наследуют ВСЕ topics parent material'а** автоматически (триггер). Это простой принцип: «материал размечен на топики X,Y → все его chunks доступны через X и Y». Selective distribution chunks по разным топикам (когда один учебник покрывает несколько билетов разными главами) — refinement post-pilot, если data покажет необходимость.

`self_check_attempts` получает FK на `program_topics(id)` (а не на свободную строку «тема», как в M2) — для устойчивого matching при дашбордах прогресса (BDD 3.2) и аналитике научрука (BDD 5.1). Существующие attempts из M2 (если есть) при миграции получают `topic_id = NULL`; в дашборде они помечены как «архивные без билета» и исключаются из per-bilet статистик.

При замене программы (BDD 7.4): новая `programs` запись со status=`active`, старая — `archived`. Existing attempts остаются с FK на topic_id из архивной программы; запрос для дашборда фильтрует и группирует по `program.status`.

**M4.5.C — Mapping источник → билет (≈3–5 дней, преимущественно ручная).**

**Шаг 0 — backfill существующих M2-материалов.** Born&Wolf, Матвеев, Yariv после rename'а `default → optics-kafedra` оказываются в кафедральном тенанте без топик-разметки. Первое действие в M4.5.C — пройти каждый из них через тот же flow ниже, чтобы они стали частью topic-mode корпуса. Без этого topic-фильтр на них не работает.

Процесс для tenant-admin (применяется и к новым, и к backfill):
1. Загрузить материал через UI с **обязательным** указанием топиков (multi-select из активной программы тенанта; minimum 1, без топиков загрузка блокируется).
2. Система запускает LLM-helper: для каждого chunk'а после ingestion — промпт «какому из этих {N} топиков релевантен этот фрагмент?». Результат — **рекомендация**, не ground-truth, отображается на странице material'а.
3. tenant-admin корректирует на **material-уровне**: «все chunks этого material → топики X, Y». Bulk-only; per-chunk override отложен post-pilot (overkill для типичного учебника).
4. После подтверждения — `material_topics` фиксируется, триггер пишет `chunk_topics`.

LLM-helper использует ту же free-tier модель, что Q&A — это часть бюджета, без отдельной строки. Если LLM-helper упал/недоступен — рекомендации не показываются, tenant-admin размечает руками; flow не блокируется.

**M4.5.D — Coverage check + quality-score (≈2 дня).**

Coverage метрика на топик:
- `coverage(topic) = COUNT(DISTINCT chunk_id) FROM chunk_topics ct JOIN chunks c ON ct.chunk_id=c.id JOIN materials m ON c.material_id=m.id WHERE ct.topic_id=? AND m.status='active'`
- Стратегия пересчёта: **denormalized counter** в `program_topics.coverage_chunks INT`, учитывает только chunks от **active** материалов. Coverage-report читает счётчик за O(N_topics), без сканов.
- Триггеры пересчёта counter'а: (1) insert/update/delete на `chunk_topics`; (2) **изменение `materials.status`** (active ↔ superseded ↔ deleted) — все chunks затронутого material'а пересчитываются для соответствующих топиков. Это критично для BDD 4.13: при удалении material'а coverage по его топикам падает; при replace (status=superseded для старого + active для нового) — net-эффект может быть нулевым.
- Порог K = **5 chunks** для self-check (минимум для генерации ≥3 MC + ≥2 open-ended с разнообразием).
- Порог K_qa = **2 chunks** для Q&A в режиме билета без fallback (BDD 1.2). При < K_qa — fallback на расширение поиска.

K-пороги конфигурируются на уровне тенанта в `tenants.config` JSON-namespace по фиксированному пути:
```json
{
  "coverage": {
    "k_self_check": 5,
    "k_qa": 2
  },
  "quality": {
    "low_quality_threshold": 0.6
  }
}
```
Это единственная официальная схема per-tenant конфига для M4.5; новые поля добавляются с дефолтами и backwards-compat.

Coverage-report (BDD 4.4):
- Список билетов с `coverage`, цветовая кодировка: красный (`< K_qa`), жёлтый (`K_qa ≤ x < K`), зелёный (`≥ K`).
- Экспорт в markdown.

Quality-score формула (BDD 4.8) — эвристика на постingestion:

```
score(material) = mean(
  ratio(chunks с длиной 200..2000 символов),
  ratio(chunks без OCR-артефактов: > 95% валидной кодировки, нет последовательностей `\n` ≥ 4),
  ratio(chunks с детектированным языком RU/EN с вероятностью > 0.7)
)
low_quality = score < 0.6
```

Threshold `0.6` — стартовая калибровка. **Калибровка проводится явно** в конце M4.5.C (после backfill 3 M2-материалов и загрузки первых 2–3 новых): tenant-admin вместе с разработчиком смотрит распределение score'ов, корректирует threshold в `tenants.config` если нужно. Material с low_quality НЕ исключается из retrieval (BDD 4.8 explicit), только помечается флагом.

**M4.5.E — Eval-set v2 + повторный прогон M3 (≈3–5 дней).**

- Расширение `eval/golden_set_v1.0` → `eval/golden_set_v2.0`: + 30–50 вопросов по новым разделам программы. Минимум 1 вопрос на топик (для self-check coverage отчёта).
- Распределение new questions: 70% Q&A на новые источники, 15% formula-heavy, 15% дополнительные refusal'ы (граничные темы из соседних специальностей).
- **Топик-аннотации в JSONL.** Каждая Q&A-запись получает поле `topic_id` (внешний `external_id` из программы, например `"2.1"`). Для refusal-блока — `topic_id: null`. Это позволяет runner'у прогонять вопрос в режиме билета (BDD 1.2) и проверять, что цитаты — из правильного топика.
- Прогон `eval/runner.py` на golden_set_v2 в **двух режимах**: `topic_mode=off` (сравнимо с v1) и `topic_mode=on` (используется `topic_id` из записи). Оба прогона в `eval/results/M4.5-report.md`.
- Сравнение:
  - v1 vs v2 в режиме off — отвечает на вопрос «не сломали ли мы базу при расширении корпуса». Цель — не деградация > 0.05.
  - v2 off vs v2 on — отвечает на вопрос «помогает ли topic-mode». Ожидание — citation accuracy и faithfulness растут на topic_mode (потому что меньше шума в retrieval).
- Триггеры: при деградации v1→v2 off — корпус нуждается в дочистке либо запуске опционального milestone Hybrid retrieval; при отсутствии прироста v2 off→on — topic-mode неэффективен, пересмотреть пороги или подход.

#### Сквозная задача — Topic-mode integration

Не отдельная фаза, но реализуется параллельно во всех M4.5.A–E:
- **Retrieval API**: новый параметр `topic_id`; при заданном — фильтр `chunks.id IN (SELECT chunk_id FROM chunk_topics WHERE topic_id = ?)`. Без параметра — поведение M4 (по всему тенанту).
- **Self-check API**: `topic_id` обязателен; coverage check (M4.5.D) применяется до запуска генератора (BDD 2.1 — block при < K).
- **UI**: индикатор режима билета (BDD 1.2), tooltip на дизейбленной кнопке self-check (BDD 2.1).
- **Логи**: `topic_id`, `topic_mode_fallback` boolean (BDD 1.2 fallback).

#### Чек-лист готовности M4.5

- [ ] tenant `default` переименован в `optics-kafedra` (handoff из M4.A)
- [ ] `corpus/optics-kafedra/program.md` загружен atomic-парсером; в БД `programs` (status=active) + N `program_topics`
- [ ] Backfill M2-материалов (Born&Wolf, Матвеев, Yariv) — все размечены по топикам; chunk_topics заполнены
- [ ] Корпус расширен: ≥ 1 material per topic для большинства билетов; coverage-report зафиксирован
- [ ] Required topics enforced: загрузка material без указания топиков блокируется
- [ ] Триггер на material_topics handle INSERT/UPDATE/DELETE; chunk_topics всегда консистентны с material_topics
- [ ] Денормализованный `program_topics.coverage_chunks` обновляется триггером (включая на изменение `materials.status`); coverage-report O(N_topics); только active материалы учитываются
- [ ] `tenants.config` содержит `coverage.k_self_check`, `coverage.k_qa`, `quality.low_quality_threshold` с дефолтами
- [ ] Quality-score считается; калибровка threshold проведена и задокументирована; материалы с `low_quality=true` помечаются флагом, retrieval всё равно их использует
- [ ] Topic-mode retrieval работает: с topic_id — фильтр; без — обычный (BDD 1.2 + fallback при < K_qa)
- [ ] Self-check блокируется при coverage < K, разблокируется при ≥ K
- [ ] `eval/golden_set_v2.0` создан с `topic_id`-аннотациями; прогнан в режимах `topic_mode=off` и `topic_mode=on`
- [ ] M4.5-report.md фиксирует: v1 vs v2 (off), v2 off vs v2 on; деградации/приросты объяснены
- [ ] Архивация программы (BDD 7.4) проверена: program_topics остаются, attempts ссылаются корректно
- [ ] BDD-сценарии 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.5, 4.2, 4.3, 4.4, 4.7, 4.8, 4.13, 7.4 — проходят (17 сценариев)

**Риски:**
- **Программа как блокер.** Без формализованного документа от кафедры M4.5.A не стартует. Митигация: программа должна быть получена ДО старта M4.5 (см. roadmap §4.4); это организационная работа, не инженерная.
- **Авторские права на материалы кафедры.** Конспекты/методички — что можно грузить даже для внутрикафедрального использования? Митигация: явный разговор с научруком до M4.5.C, фиксация разрешений в `corpus/optics-kafedra/sources.md`.
- **Объём ручной разметки.** Mapping source→topic для 10–20 материалов может занять неделю. Митигация: bulk-операции в M4.5.C, LLM-helper как seed.
- **Quality-score шумит.** Эвристика может ругаться на нормальные тексты с формулами (формулы → длинные не-ASCII последовательности). Митигация: формулы детектируем отдельно (LaTeX-pattern), не штрафуем; threshold 0.6 калибруется на первых 5 материалах.
- **Coverage K=5 слишком высоко.** Может оказаться, что для редких билетов в принципе мало источников. Митигация: K — конфигурируемый параметр в `tenant.config`, для пилотного тенанта можно опустить до 3, явно зафиксировав в защите.
- **Деградация метрик на eval-set v2.** Расширенный корпус может вытащить новые retrieval-проблемы. Митигация: триггер запуска опционального milestone Hybrid retrieval при просадке formula-heavy блока.

---

### M5 — Supervisor role + learning analytics

**Длительность:** 3–4 недели

**Цель:** дать научруку видимость того, где буксуют его аспиранты, без превращения системы в инструмент слежки.

**Scope (in):**
- Новая роль `supervisor` per tenant.
- Дашборд научрука:
  - **Heatmap по билетам** — где аспирантам нужна помощь (агрегат по группе, упорядочен по доле неуспешных attempts).
  - **Drilldown в проблемный билет** — детали по теме: счётчики, частые `error_tags` из self-check evaluator (generic learning issues — `factual_error`, `incomplete`, `logic_gap`), частые причины refusal.
  - **Per-student progress** — только при явном opt-in аспиранта; по умолчанию scrub до анонимного.
- **First-time experience научрука** — onboarding-страница с превью heatmap на демо-данных, объяснением privacy-политики и текущим состоянием тенанта. Без этого пилот теряет научрука в первый же день (см. BDD 5.6).
- **Список аспирантов тенанта** с разделением на opt-in (видны email и переход в карточку) и без opt-in (анонимизированно).
- Privacy: дефолт — анонимные агрегаты по группе ≥ N студентов; персональные данные только с consent.

> **Не входит в M5:** concept-tagging (контролируемый словарь концептов или динамический LLM-tagging) и concept confusions. Решение от v0.5: эта аналитика второго порядка перенесена в зону роста post-M6. Per-bilet аналитики достаточно для пилотной ценности научруку.

**Scope (out):**
- Полноценная gradebook-функциональность.
- Push-нотификации научруку.
- Сравнение между кафедрами.

**Артефакты:**
- Спека `docs/specs/supervisor-analytics.md`.
- Новый раздел в `docs/governance.md` про privacy и consent.
- UI-страницы дашборда.

**Defense narrative:**
> «Научрук получает учебную "погодную карту" группы, а не инструмент надзора. Дефолт — анонимные агрегаты, персональные данные — только по явному согласию.»

#### Подробный план M5

**M5.A — Schema additions (≈1–2 дня).**

Часть schema-изменений M5 закрывает дыры M4/M4.5 (поля topic_id и status, которые понадобились только в M5 при формулировке аналитики).

```sql
-- Privacy & visibility (новое для M5)
ALTER TABLE users ADD COLUMN supervisor_visibility TEXT NOT NULL DEFAULT 'anonymous-aggregate-only';
-- enum: 'anonymous-aggregate-only' | 'show-to-supervisor'
ALTER TABLE users ADD COLUMN visibility_changed_at TIMESTAMPTZ;

-- Status явный enum (закрывает гэп от M2: status упоминался в BDD 2.3, 2.5, но не зафиксирован в schema)
ALTER TABLE self_check_attempts ADD COLUMN status TEXT NOT NULL DEFAULT 'completed';
-- enum: 'in_progress' | 'completed' | 'abandoned' | 'invalid_evaluation'
-- Backfill: все существующие → 'completed' (M2 не имел понятия abandoned)

-- Topic_id на Q&A-уровне (закрывает гэп M4.5: упоминался в BDD 1.2, но не было FK)
ALTER TABLE qa_sessions ADD COLUMN topic_id UUID REFERENCES program_topics(id) ON DELETE RESTRICT;
-- NULL для сессий без topic-mode; NOT NULL невозможно (свободный Q&A в режиме без билета — BDD 1.1)

-- Индексы для heatmap/drilldown queries:
CREATE INDEX self_check_attempts_topic_tenant_status
  ON self_check_attempts (topic_id, tenant_id, status);
CREATE INDEX qa_sessions_topic_tenant
  ON qa_sessions (topic_id, tenant_id) WHERE topic_id IS NOT NULL;
```

`self_check_attempts.error_tags TEXT[]` — поле от M2 self-check evaluator. Если в M2 это в `evaluator_summary` JSON, миграцией извлечь в массив для индексации; enum: `factual_error`, `incomplete`, `logic_gap`, `terminology` (generic learning issues, не concept-уровень).

Расширения `tenants.config`:
```json
{
  "analytics": {
    "min_aggregate_size": 5,        // BDD 5.3 N-порог по студентам
    "min_attempts_for_heatmap": 30  // BDD 5.1 нижний порог общего числа attempts
  }
}
```

**M5.B — Aggregation queries (≈4–5 дней).**

Все запросы по аналитике строятся как параметризованные SQL-views и проверяют N-порог и tenant-isolation на уровне SQL (двойная защита: middleware + query).

Heatmap (BDD 5.1):

```sql
WITH topic_stats AS (
  SELECT
    pt.id AS topic_id,
    pt.section,
    pt.title,
    pt.external_id,
    COUNT(DISTINCT a.id) AS attempts_total,
    COUNT(DISTINCT CASE WHEN a.overall_score < 3 THEN a.id END) AS attempts_below_threshold,
    COUNT(DISTINCT a.user_id) AS distinct_users
  FROM program_topics pt
  LEFT JOIN self_check_attempts a ON a.topic_id = pt.id
  WHERE pt.program_id = (SELECT id FROM programs WHERE tenant_id = :tenant AND status = 'active')
    AND a.tenant_id = :tenant
    AND a.status = 'completed'           -- исключаем abandoned (BDD 2.5)
  GROUP BY pt.id, pt.section, pt.title, pt.external_id
)
SELECT *,
  attempts_below_threshold::numeric / NULLIF(attempts_total, 0) AS fail_rate
FROM topic_stats
ORDER BY fail_rate DESC NULLS LAST;
-- ci_low / ci_high (Wilson 95%) вычисляются в app-коде из attempts_below_threshold и attempts_total
-- топики с attempts_total = 0 показываются последними как «нет данных», не удаляются из выдачи
```

**Двойной gate для heatmap (BDD 5.1 + 5.3):** оба условия должны выполняться, иначе heatmap не показывается.

```python
# psuedocode для guard'а перед heatmap
def can_show_heatmap(tenant):
    n_students = count_students_active(tenant)
    n_attempts = count_completed_attempts(tenant)
    cfg = tenant.config['analytics']
    return n_students >= cfg['min_aggregate_size'] and n_attempts >= cfg['min_attempts_for_heatmap']
```

При невыполнении любого условия — UI показывает onboarding-страницу (BDD 5.6) с прогнозом «нужно ещё X студентов и Y attempts». Это унифицирует поведение «недостаточно данных» — нет двух разных пустых состояний.

**Wilson confidence interval** в PostgreSQL нативно отсутствует. Реализация: **в app-коде** на этапе сериализации результата heatmap (Python: scipy.stats или ручная формула). SQL возвращает только `attempts_below_threshold` и `attempts_total`; CI вычисляется в Python. Это упрощает миграции (не нужна UDF) и тесты (юнит-тест на одну функцию).

Drilldown по топику (BDD 5.2):

```sql
-- per-attempt breakdown без user_id (анонимный агрегат)
SELECT
  unnest(error_tags) AS error_tag,
  COUNT(*) AS occurrences
FROM self_check_attempts
WHERE topic_id = :topic AND tenant_id = :tenant AND status = 'completed'
GROUP BY error_tag
ORDER BY occurrences DESC LIMIT 10;

-- частые причины refusal на этой теме (только сессии в topic-mode)
SELECT m.refusal_reason, COUNT(*) AS occurrences
FROM qa_sessions s
JOIN qa_messages m ON m.session_id = s.id
WHERE s.topic_id = :topic AND s.tenant_id = :tenant AND m.refusal_reason IS NOT NULL
GROUP BY m.refusal_reason
ORDER BY occurrences DESC;
-- Refusals от свободного Q&A (без topic-mode) НЕ учитываются: невозможно достоверно отнести их к конкретному билету.
```

> **Замечание о refusal_reason:** поле `qa_messages.refusal_reason` наследуется из M2 (упоминается в product-proposal §6.2). Если в M2 хранится в JSON — миграция M5 извлекает в отдельную колонку для индексации. Если уже отдельная — без изменений.

Учёт abandoned attempts (BDD 2.5): включается в общий count attempts_total, но не в `attempts_below_threshold` (некорректно считать abandoned за «не сдал»).

Учёт soft-deleted users (BDD 7.3): их attempts остались с `user_id = NULL`, сами attempts учитываются в heatmap (это контент-сигнал, не персональный). Distinct_users считаем только non-NULL.

**M5.C — Privacy enforcement и audit (≈3 дня).**

Middleware-проверки на каждом запросе к persona-level data:

```python
# psuedocode
def check_personal_access(viewer, target_user):
    if viewer.role == 'super-admin': return True  # cross-tenant, для governance/export
    if viewer.tenant_id != target_user.tenant_id: raise Forbidden
    if viewer.id == target_user.id: return True   # доступ к своей карточке
    if viewer.role == 'tenant-admin':
        # tenant-admin НЕ имеет доступа к персональным attempts кроме как через governance flow (BDD 7.3)
        return is_governance_action()
    if viewer.role == 'supervisor':
        if target_user.supervisor_visibility != 'show-to-supervisor':
            audit_log('privacy-violation-attempt', actor=viewer, target=target_user)
            raise NotFound  # 404, не 403 — не палим существование (как cross-tenant в M4.D)
        audit_log('personal_data.access', actor=viewer, target=target_user)
        return True
    raise Forbidden
```

Audit-события M5:
- `personal_data.access` — на каждое открытие персональной карточки аспиранта (BDD 5.4)
- `privacy-violation-attempt` — на попытку доступа без opt-in (BDD 5.5)
- `visibility.toggle` — на изменение `supervisor_visibility` аспирантом (BDD 3.4)
- `analytics.dashboard.access` — НЕ пишем (слишком шумно, агрегаты публичны для роли)

Visibility toggle (BDD 3.4):
- При смене `supervisor_visibility` пишется audit log + обновляется `visibility_changed_at`
- Кеш в supervisor session не используется — каждый запрос проверяет текущее значение `supervisor_visibility` (это критично для «при возврате прежний доступ научрука прекращается немедленно»).

**M5.D — UI pages (≈5 дней).**

Новые страницы:

| Страница | Роль | BDD |
|---|---|---|
| Onboarding научрука | supervisor (при N<min_aggregate_size или attempts<30) | 5.6 |
| Heatmap дашборд | supervisor (при достаточных данных) | 5.1 |
| Drilldown в билет | supervisor | 5.2 |
| Список аспирантов | supervisor | 5.7 |
| Персональная карточка аспиранта | supervisor (при opt-in) | 5.4 |
| Privacy-настройки в профиле | student | 3.4 |

Анонимизация в списке аспирантов (BDD 5.7): для students без opt-in отображается ordinal label `Аспирант #N` стабильно (детерминированно: `ROW_NUMBER() OVER (ORDER BY user_id)` per tenant; not by `user_id` напрямую — иначе разглашаем порядок регистрации).

#### Сквозная задача — Demo data для onboarding-страницы

Для BDD 5.6 (превью heatmap до накопления реальных данных) — три состояния по уровню готовности тенанта:

| Состояние | Что показывает onboarding | Когда применяется |
|---|---|---|
| **Программа не загружена** | «Кафедра ещё готовит программу. Когда tenant-admin загрузит программу и материалы, здесь появится дашборд по вашим билетам» | program не существует или status='archived' и нет active |
| **Программа есть, недостаточно данных** | Превью heatmap по **реальным билетам тенанта** с **синтетическими числами**; плашка «пример данных, реальная картина появится после X студентов и Y attempts» | active program существует, gate `can_show_heatmap` = false |
| **Достаточно данных** | Реальный heatmap (BDD 5.1) | gate = true |

Синтетические числа для второго состояния — статический JSON в коде, одинаковый для всех тенантов; только лейблы билетов берутся из реальной программы.

#### Чек-лист готовности M5

- [ ] `users.supervisor_visibility` + `visibility_changed_at` мигрированы; default = `'anonymous-aggregate-only'`
- [ ] `self_check_attempts.status` enum (`in_progress`/`completed`/`abandoned`/`invalid_evaluation`) добавлен; backfill существующих в `'completed'`
- [ ] `qa_sessions.topic_id` FK на `program_topics` добавлен (nullable); индексы на heatmap/drilldown queries созданы
- [ ] `tenants.config.analytics` содержит `min_aggregate_size=5`, `min_attempts_for_heatmap=30`
- [ ] **Двойной gate heatmap**: оба условия (N_students ≥ 5 AND N_attempts ≥ 30) проверяются; при невыполнении — onboarding-страница (не пустой heatmap)
- [ ] Wilson 95% CI вычисляется в app-коде; SQL возвращает только `attempts_below_threshold` и `attempts_total`
- [ ] Drilldown по билету: error_tags + refusal_reasons (только из topic-mode сессий); abandoned attempts исключены из «не сдал»; soft-deleted users учитываются в content-агрегатах
- [ ] Privacy middleware: 404 на попытку открыть карточку без opt-in; запись в audit log
- [ ] Visibility toggle применяется немедленно (no caching); audit log + `visibility_changed_at`
- [ ] Onboarding покрывает 3 состояния (нет программы / недостаточно данных / готов); превью с реальной программой только во 2-м состоянии
- [ ] Список аспирантов: opt-in видны с email, без opt-in — `Аспирант #N` стабильным ordinal'ом; deleted_at IS NOT NULL не отображаются
- [ ] BDD-сценарии 3.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7 — проходят (8 сценариев)
- [ ] DPIA-lite раздел добавлен в `docs/governance.md` (основания обработки персональных данных аспирантов, опции отзыва согласия и удаления)

**Риски:**
- **Privacy в РФ.** Требования к персданным аспирантов могут потребовать DPIA-lite раздел в governance до пилота. Митигация: явная задача в M5.C — обновить `docs/governance.md` с разделом про hosting persona-level data, основания обработки, опции удаления (BDD 7.3).
- **Поведение при тонких данных.** На пилоте 3–5 аспирантов heatmap **никогда** не покажется (N < 5). Митигация: либо понизить `min_aggregate_size` до 3 явно в `tenants.config` для пилота, либо принять что в первые недели supervisor видит только onboarding-страницу (это явно зафиксировано как валидное поведение).
- **Демо-данные дезинформируют.** Если синтетические числа на onboarding слишком похожи на реальные — научрук будет принимать решения по фейку. Митигация: явная плашка «пример данных», статистика числа attempts в углу страницы.
- **Anonymization stability.** Ordinal `Аспирант #3` стабилен в рамках tenant'а, но при добавлении нового студента старые ordinal'ы могут поплыть. Митигация: `ROW_NUMBER() OVER (ORDER BY id)` гарантирует, что новый студент получает следующий номер; существующие не меняются.
- **Кеш Wilson CI.** Heatmap может пересчитываться часто. Митигация: для пилота 3–5 аспирантов — реал-тайм без кеша; на росте — materialized view с refresh раз в N минут.

---

---

### M6 — Пилот на кафедре оптики

**Длительность:** 1–2 месяца календарных, ~1–2 недели инженерных

**Цель:** довести систему до реального использования аспирантами кафедры оптики, готовящимися к кандэкзамену. Это переводит проект из «прототип» в «работает у людей».

**Scope (in):**
- 3–5 аспирантов кафедры оптики + 1 научрук/завкафедрой как наблюдатель с supervisor-доступом.
- Корпус — `optics-kafedra` (расширенный в M4.5).
- Сбор телеметрии (метрики M3 в проде на живом потоке) + опросник раз в 2 недели.
- Минимальный хостинг — обсудить отдельно (см. cross-cutting §3.1): можно временный VPS либо локальный сервер кафедры.
- Pilot-report: что работало, что нет, какие темы программы системе даются хуже всего, что говорят пользователи, какие концепты чаще всего вызывают confusions (вход для будущих итераций supervisor-аналитики).

**Scope (out):**
- Не масштабируем на вторую кафедру одновременно.
- Не делаем продакшн-деплой с SLA.

**Артефакты:**
- `docs/pilot-report.md`.
- Опросник + сырые ответы (анонимизированные).
- Сравнение метрик M3 на синтетическом eval-set vs реальном использовании (где система проседает на практике, чего eval-set не ловит).

**Defense narrative:**
> «3–5 настоящих аспирантов кафедры оптики, 8 недель подготовки к кандэкзамену, корпус — реальная программа кафедры, научрук видит дашборд прогресса. Вот что они говорят, вот цифры из телеметрии.»

#### Подробный план M6

M6 — преимущественно организационный milestone. Инженерные подзадачи (M6.A, M6.B) делаются ДО запуска пилота; пилотный run (M6.C) длится 8 недель календарных при ~1 ч/день поддержки разработчика; пост-обработка (M6.D, M6.E) — после.

**M6.A — Pre-pilot infrastructure (≈1–2 недели до запуска).**

Hosting (закрывает organisational open question §4.7):
- **Hetzner Cloud CX22** или аналог: 2 vCPU, 4 ГБ RAM, ~€5–7/мес. Достаточно для одного тенанта × 5 пользователей × Postgres + embeddings + FastAPI. Полностью umещаются в RAM с маржой.
- Альтернативы: сервер кафедры (если есть готовый и админ согласен), DigitalOcean. AWS/GCP избыточно дороги для пилота.
- Один dedicated host, всё в одном `docker-compose.yml`. Managed Postgres — out of scope (overkill).

Domain + HTTPS:
- Subdomain типа `atlas-optics.{your-domain}` либо одноразовый домен через Cloudflare.
- HTTPS через Caddy/Traefik (auto Let's Encrypt) как reverse proxy перед FastAPI.

Deployment:
- **Image build**: GitHub Actions на push в `main` → собирает образ → пушит в GHCR с тегом `{commit_sha}` и `latest`. Сам build автоматизирован, **деплой — нет**.
- **Деплой на VPS**: разработчик руками: `ssh prod && cd atlas && git pull && docker-compose pull && docker-compose up -d` (либо скрипт `scripts/deploy.sh`). Каждый деплой — осознанное решение разработчика.
- **Migrations**: явный manual шаг **до** перезапуска сервиса: `docker-compose run --rm app alembic upgrade head`. **Не** на старте контейнера автоматически — упавшая миграция не должна валить весь сервис; разработчик видит ошибку до перезапуска.
- **Rollback**: переключение на предыдущий тег image'а в `.env` (`IMAGE_TAG=...`) + `docker-compose up -d`. Если миграция была применена — отдельный `alembic downgrade -1` (только если миграция reversible; при необратимых — restore из backup'а).
- **Downtime allowed**: для пилота 5 пользователей принимаем ~30 секунд при rolling restart.

Backup:
- `pg_dump` раз в сутки cron'ом, ретенция 7 дней. Хранение — на том же VPS (для пилота достаточно; offsite backup post-pilot, если решим продолжать).
- **Backup секретов отдельно**: `.env` на VPS лежит в `/opt/atlas/.env` с `chmod 600` (только root читает). Копия `.env` — в зашифрованном password manager разработчика (1Password / Bitwarden); НЕ в git. При смене любого секрета — синхронизация обоих мест ручная.

Secret management:
- `LLM_API_KEY`, `JWT_SECRET`, `ADMIN_PASSWORD`, `POSTGRES_PASSWORD` — в `.env` на VPS. Docker-compose читает через `env_file`.
- Никаких секретов в репозитории, в логах (Sentry-фильтр), в audit_log.details (sanitization helper).
- Rotation: для пилота — нет автоматического (8 недель — приемлемо). При утечке — manual rotate + redeploy.

Monitoring (минимум для пилота):
- **Structured JSON logs** уже есть от M2; логи из контейнеров → файл с ротацией.
- **Sentry free tier** для exception-tracking.
- **Daily manual check** разработчиком: `tail -F` логов + проверка количества ошибок за сутки.
- **Daily metrics report** (`scripts/daily_metrics_report.py` cron'ом): за прошедшие сутки агрегирует faithfulness (по judged sample), citation accuracy, refusal rate, error rate, активность пользователей. Шлёт в Telegram-чат разработчика. **Это даёт сигнал «просадка > 0.10 от baseline»** — без этого триггер из M6.C сформулирован, но не отслеживаем.
- Никаких Prometheus/Grafana — overkill для 5 пользователей.

Runbook (артефакт `docs/runbook.md`):
- Как перезапустить упавший сервис.
- Как достать логи за конкретный request_id.
- Как сделать ad-hoc backup перед изменением.
- Как переключиться на rollback-image.
- Как ответить на типичные user-сообщения («не работает» → запросить request_id; «хочу удалить аккаунт» → процесс BDD 7.3).

**M6.B — Onboarding пилотных пользователей (≈1 неделя).**

Pre-flight checklist (до приглашения первого аспиранта):
- [ ] Tenant `optics-kafedra` существует, программа загружена, coverage по большинству билетов ≥ K=5
- [ ] Eval-set v2 прогнан в проде, метрики не хуже v2-stage (sanity check)
- [ ] Tenant-admin (методист или сам научрук) зарегистрирован, прошёл краткий guide
- [ ] Welcome-материалы готовы (см. ниже)
- [ ] Communication channel работает (Telegram-чат пилотной группы создан, разработчик в нём)
- [ ] DPIA-lite раздел в governance подписан/утверждён ответственным с кафедры

Welcome-материалы (web-страницы внутри UI, доступны при первом входе и из меню):
- **Аспиранту** (1 экран): как зарегистрироваться → открыть билет → задать вопрос или пройти self-check → как сообщить о плохом ответе → privacy-настройки.
- **Научруку** (1 экран): что видно в дашборде → privacy-политика → как ваши действия логируются → ссылка на Q&A для самостоятельного теста.
- **Tenant-admin'у** (1 экран): как загружать материалы → coverage-report → user feedback → governance-flow при удалении данных.

Onboarding-волна (последовательно, не одновременно):
1. День 0: tenant-admin полностью готов, материалы загружены.
2. День 1–2: научрук приглашён, проходит onboarding (BDD 5.6 «нет данных» состояние).
3. День 3–7: аспиранты приглашаются по одному (не пакетом). Каждый — invite + welcome-сообщение в Telegram-чате. Это даёт 5 раздельных smoke-тестов consent-flow.

Reissue invite (если 7 дней истекли без redemption):
- Старый invite автоматически инвалидируется (BDD 4.6).
- tenant-admin генерирует новый invite через UI; в audit_log пишутся обе записи (старый expired, новый created).
- На пилоте — ожидание следующих 7 дней нормальное; если 14+ дней без активности → разговор с научруком, готов ли аспирант вообще.

Ответственное лицо с кафедры за DPIA-lite — это **либо tenant-admin** (если методист), **либо научрук** (если совмещает роли). Подпись = явное согласие в тексте email/Telegram, фиксируется в `docs/governance.md` § «Подписанты политики».

**M6.C — Run (8 недель).**

Поддержка разработчика:
- **Daily**: 5–15 минут — проверка логов на ERROR, ответ на сообщения в Telegram-чате.
- **Weekly check-in** с tenant-admin / научруком: 30 минут видео-созвон. «Что работало, что не работало, какие фидбеки от аспирантов?». Заметки в `docs/pilot-log.md`.
- **Reactive support**: ответ на сообщения в Telegram-чате в течение рабочего дня.

Кадры активных вмешательств (если что-то идёт не по плану):
- Метрики качества проседают > 0.10 от baseline (видим из daily metrics report) → разбор полётов, возможно фикс retrieval / промптов.
- Аспиранты не активны (< 3 attempts/неделю на человека) → разговор с научруком: motivation issue или баг блокирует?
- Privacy incident — см. ниже отдельный playbook.

**Privacy incident playbook** (оформляется в `docs/runbook.md`):

Определение incident'а:
- **НЕ incident**: middleware заблокировал попытку доступа (`privacy-violation-attempt` в audit_log) — это работает по дизайну (BDD 5.5).
- **Incident**: persona-level data реально попала к роли, у которой не должно быть доступа. Например: bug в SQL-фильтре показал научруку attempts студента без opt-in; export'ом ушли данные другого тенанта; в логах Sentry видны email/имена.

Шаги при incident'е:
1. **Containment**: немедленно отключить затронутый endpoint (feature flag или revert image к pre-incident версии).
2. **Assessment**: определить scope — кто увидел чьи данные за какой период. Запрос к audit_log + access logs.
3. **Notification**: затронутые пользователи уведомляются в течение 24 часов (через `outbound_emails` table — manual проверка и отправка).
4. **Fix + verification**: bug-fix + regression-test перед redeploy.
5. **Post-mortem**: запись в `docs/incidents/YYYY-MM-DD-description.md` с timeline, причиной, фиксом, выводами для prevention.
6. Если incident серьёзный (≥ 1 пользователя реально затронут) — пилот может быть приостановлен по решению разработчика + кафедрального ответственного.

**Reactive support**: ответ на сообщения в Telegram-чате — целевая в течение рабочего дня (9:00–20:00 по МСК); ночью / выходных — best-effort, без SLA. На onboarding-странице каждой роли явно указано: «срочные проблемы — в Telegram, ответ в рабочие часы».

Surveys:
- **Mid-pilot survey (неделя 4)** — 5–7 вопросов на 3 минуты. Что используется? Что мешает? Что добавить?
- **End-pilot survey (неделя 8)** — повтор + специфичные «продолжите ли использовать», «помогло ли в подготовке», «что критически важно изменить».
- **Хостинг survey**: внутри ATLAS UI как анонимная форма (поле `surveys.responses` в БД с tenant_id, без user_id). Не Google Forms — данные не должны уходить к third party без явного согласия. Альтернатива на пилоте (если внутренняя форма — лишний инжиниринг): markdown-anketa в Telegram-чате с явной плашкой «ваш ответ виден разработчику и научруку».

Отзыв доступа после пилота: явно фиксируется, что после неделя 9 доступ остаётся, но активная поддержка прекращается до решений из M6.E.

**M6.D — Telemetry (continuous через весь run).**

Накапливаем в проде:
- **Production-метрики качества**: LLM-judge faithfulness и citation accuracy (как в M3-runner, но in-band). **Sampling**: каждый 10-й Q&A с `expected_behavior='answer'` (не refused) попадает в judge-очередь; refused-запросы не judging'уем (нечего проверять). Это даёт ~10% reproducible coverage без bias к лёгким вопросам. Бюджет API: ~5–10 USD/мес сверх базы.
- **Behavioral metrics**: per-user — Q&A count, self-check count, topics touched, attempts per topic; по тенанту — daily active users, weekly retention. Хранение — в `prod_metrics_daily` table (агрегаты), не в audit_log.
- **User feedback signals (BDD 1.8)**: count of "incorrect answer" reports, % от total Q&A. Каждое flag — кандидат в eval-set v3.
- **Сравнение с eval v2**: где prod-метрики хуже синтетических — это указатель на пробелы eval-set.

Privacy в телеметрии:
- **Default — анонимные агрегаты для всех ролей**, включая разработчика. Persona-level (per-user breakdown) видим:
  - Аспиранту: всегда (свои данные).
  - Научруку: при `supervisor_visibility = 'show-to-supervisor'` (BDD 3.4).
  - Разработчику: только в рамках incident response или явного запроса debug'а (с записью в audit log `dev.persona_access`). По умолчанию dev видит только агрегаты + анонимизированный sample (Аспирант #N, как в BDD 5.7).
- Эта политика фиксируется в DPIA-lite разделе governance.

**M6.E — Pilot report и решения (≈1 неделя после).**

Артефакт: `docs/pilot-report.md`, структура:
1. **Что было**: даты, сетап, участники (анонимизированно), длительность.
2. **Quantitative**: финальные prod-метрики (faithfulness, citation accuracy, refusal precision, latency, retention, активность). Сравнение с eval v2.
3. **Qualitative**: сводка surveys + цитаты из Telegram (с разрешения авторов).
4. **Что работало**: 3–5 validated wins → в defense narrative.
5. **Что не работало**: 3–5 пробелов с разбором (баг? UX? eval-set? архитектура?).
6. **Decisions framework** — каждый пробел классифицируется:
   - Critical fix (чинить срочно, blocker для повторного запуска).
   - UX backlog (не блокирующий, в очередь к next iteration).
   - Зона роста (отложено в roadmap §5).
   - Re-scope (требует пересмотра подхода — опциональный milestone Hybrid retrieval, etc.).

Pilot success criteria (для бинарного «успех/неуспех»):
- **Активность**: ≥ 80% зарегистрированных аспирантов сделали ≥ 12 self-check attempts за пилот (8 недель ≈ 1.5 attempts/неделю — это «гуляли», не «зашли один раз»).
- **Использование супервайзером**: ≥ 8 сессий научрука за пилот (≥ 1 в неделю в среднем).
- **Качество ответов**: ≤ 10% Q&A помечены пользователями как «incorrect».
- **Удержание**: end-pilot survey — ≥ 60% «продолжили бы использовать».
- **Privacy**: 0 **подтверждённых incident'ов** (попытки заблокированные middleware — не incident; реальный leak personal data — incident, см. playbook M6.C).

Все 5 — успех. ≤ 2 не выполнены — частичный успех (защита всё равно сильная, decisions framework определяет дальнейшее). 3+ не выполнены — пилот неуспешный, нужен серьёзный пересмотр.

#### Чек-лист готовности M6

**До запуска (M6.A + M6.B):**
- [ ] VPS поднят, домен + HTTPS работают
- [ ] GitHub Actions собирает image в GHCR на push в main
- [ ] `scripts/deploy.sh` работает (manual) с rollback процедурой; alembic upgrade head — отдельный manual шаг до restart
- [ ] Smoke-тест AT-01 (Q&A с цитатами) проходит на проде
- [ ] Backup-cron работает, протестирован restore из последнего dump'а
- [ ] `.env` лежит на VPS с chmod 600; копия в password manager разработчика; rotation-инструкция в runbook
- [ ] Sentry ловит exceptions; sanitization helper фильтрует секреты из payloads
- [ ] `scripts/daily_metrics_report.py` cron'ом шлёт ежедневный отчёт в Telegram-чат разработчика
- [ ] Runbook (`docs/runbook.md`) написан, включая privacy incident playbook (containment → assessment → notification → fix → post-mortem)
- [ ] Tenant `optics-kafedra` готов к пилоту (отчёт BDD 4.5 = «GO»)
- [ ] Welcome-страницы для 3 ролей готовы и доступны в UI; явно фиксируют поддержку «9–20 МСК, ночью best-effort»
- [ ] Telegram-чат пилотной группы создан
- [ ] DPIA-lite раздел в governance.md подписан кафедральным ответственным; политика persona-level доступа разработчика зафиксирована

**Run (M6.C — гейты):**
- [ ] Mid-pilot survey собран (≥ 70% response rate)
- [ ] Weekly check-in заметки ведутся в `docs/pilot-log.md`
- [ ] Privacy-инцидентов = 0 (если есть — incident-flow задокументирован)

**После (M6.E):**
- [ ] End-pilot survey собран
- [ ] `docs/pilot-report.md` зафиксирован со всеми 6 разделами
- [ ] Pilot success criteria — посчитаны и зафиксированы
- [ ] Decisions framework заполнен; каждый пробел отнесён в одну из 4 категорий
- [ ] Defense narrative обновлён real-world цифрами и цитатами

**Риски:**
- **Кафедра как блокер.** Должна быть закрыта **до M4** (см. §4.2). Если за 2 недели до планового начала M6 кафедра не подтверждена — пилот переносится, M3-метрики и инфра остаются как defense story.
- **Аспиранты не активны.** Митигация: weekly check-in с научруком, при просадке — разговор с группой о причинах. План B: продлить пилот на 4 недели.
- **Production-баги не воспроизводятся локально.** Митигация: structured logs с request_id; runbook'овая команда `scripts/grab-logs.sh <request_id>` выгружает все события по конкретному запросу.
- **Privacy incident.** Митигация: на старте пилота — code review всех privacy-related путей с эмулированными попытками доступа без opt-in (BDD 5.5); incident playbook в runbook.
- **Кафедра уезжает на каникулы / экзаменационная сессия.** Митигация: явно подтвердить с научруком, что 8 weeks не пересекаются с фазами, когда аспиранты заведомо неактивны.
- **VPS падает.** Митигация: SLA Hetzner — 99.9%, неподходящих часов в 8 недель ~6. Backup + daily cron + runbook процесс восстановления.
- **Бюджет API превышен.** Митигация: лимит на OpenRouter в проде; при достижении 80% — алерт; sample telemetry-judge можно временно выключить.

---

## 3. Cross-cutting concerns

### 3.1 Hardware budget

**M1 8GB (dev environment)** — для разработки и локального тестирования всех milestones до M6:
- M3: только дополнительный eval-runner, нагрузки не добавляет.
- M4–M4.5: расширенный корпус — больший индекс. Born&Wolf+Матвеев+Yariv ≈ X тыс. чанков; полная программа кафедры может вырасти до 10× (грубо). pgvector с HNSW справится, но при ingestion временно может пиково жать память. Загрузку делать порциями.
- M5: индексы и tenant-фильтры — на постгрес, в пределах профиля.
- LLM-judge для eval — через API, не локально.

**Hetzner CX22 (production для M6)** — 2 vCPU, 4 ГБ RAM, ~€5–7/мес. Зафиксировано в [§M6.A](#m6--пилот-на-кафедре-оптики). Хватает на одного тенанта × 5 пользователей; всё умещается в RAM с маржой.

### 3.2 Бюджет API

- M3 один прогон eval-set v1 ≈ 120 запросов × ~6k токенов ≈ 700k токенов. На judge — ещё ×1.5. Единицы долларов за прогон.
- M4.5: повторный прогон на расширенном eval-set v2 — порядка $5–10.
- Пилот в M6: 3–5 аспирантов × ~10 запросов/день × 8 недель ≈ 1500 запросов. В текущий лимит 90–150 USD/мес из `product-proposal.md` §4.3 укладывается с большим запасом.
- **Production telemetry M5/M6**: LLM-judge на 10% sample реальных Q&A — ~$5–10/мес сверх базы. Лимит на OpenRouter в проде; алерт при достижении 80%; sample-judge можно временно выключить.

### 3.3 Зависимости между milestones

```
M3 (eval baseline) ──┬──► Hybrid retrieval (опциональный milestone)
                     │
                     └──► M4.5 (нужен runner, чтобы измерить эффект расширения корпуса)

M4 (multi-tenant) ──► M4.5 (корпус кафедры) ──► M5 (supervisor) ──► M6 (пилот)
```

M3 и M4 можно вести параллельно. M4.5 требует обоих. M5 и M6 — последовательно. Опциональный Hybrid retrieval вставляется по триггеру (см. M3 риски).

### 3.4 Связь с уже зафиксированными зонами роста

| Зона из product-proposal | Куда уехала в roadmap |
|---|---|
| §7.2 Hybrid retrieval | Опциональный milestone «Hybrid retrieval» (между M3 и M4) |
| §7.5 Персонализация | **сознательно вне этого roadmap** — после M6, как следующий цикл |
| §7.6 Full 3-step self-check | вне M3–M6; рассмотреть после пилота, если данные M6 покажут запрос на более качественный feedback |

---

## 4. Open questions для следующей итерации

### Открытые (требуют решения до соответствующего milestone)

1. **Когда следующая защита?** От этого зависит, сколько milestones реалистично уложить. 2–3 месяца ≈ M3 + M4. 4–6 месяцев ≈ M3 + M4 + M4.5 + M5. Полный путь до M6 — 6–9 месяцев.
2. **Кафедра.** Есть ли реальная кафедра оптики, готовая на пилот? Кто конкретно — научрук, завкафедрой, кто-то ещё? Без этого вся ось A теряет якорь, а M4.5 нечем наполнять. **Это блокер для всего после M3 — закрыть как можно раньше.**
3. **Профиль кафедры в оптике.** Оптика — широкое поле: классическая, лазерная, нелинейная, квантовая, ВОЛС, биомедицинская. Какой профиль у конкретной кафедры? От этого зависит, какие учебники докрывают пробелы текущих 3 томов.
4. **Программа кандэкзамена.** В каком виде существует у кафедры — официальный документ с разделами, устные традиции, актуализированный список билетов? Если только устно — M4.5 начнётся со сбора и формализации.
5. **Авторские права на материалы кафедры.** Лекции, конспекты, методички кафедры — что разрешено грузить в систему даже для внутрикафедрального использования? Решить с научруком до M4.5.
6. **Готовность к платному LLM на eval-judge.** Free-tier Qwen 8B как judge для faithfulness может шуметь. Один прогон на платной модели — единицы долларов; нужен ли он или хватит free-tier?

### Закрытые

| Вопрос | Решение | Где зафиксировано |
|---|---|---|
| **topic-mode** | Hard toggle с асимметричным fallback (Q&A расширяет, self-check блокируется) | [bdd-scenarios.md §9](bdd-scenarios.md), сценарии 1.2 + 2.1 |
| **concept-tagging** | Skip в M5, вынесено в зону роста post-M6 | [bdd-scenarios.md §10](bdd-scenarios.md) |
| **program-versioning** | Hard archive on replace + UX-разделение архивных attempts | BDD 7.4, M4.5.B |
| **Хостинг для пилота** | Hetzner CX22 €5–7/мес | M6.A, §3.1 |
| **Privacy posture** | DPIA-lite раздел в governance + явная политика persona-доступа | M5.C + M6.A, гейт перед запуском |

---

## 5. Что НЕ делаем (явный out-of-scope)

### Из-за позиционирования (обучающая среда, не аттестационная)
- Апелляции, пересмотр оценок self-check.
- Формальные аттестационные решения, сертификаты, итоговые баллы кандэкзамена внутри системы.
- Proctoring / anti-cheating режим.

### Стратегические решения
- **Публикационный трек** — статья, препринт, paper, arXiv, ВАК. Фокус на продукте.
- Полный персонализированный adaptive tutor с моделью ученика (откладывается post-M6).
- Telegram-бот.
- Расширение на не-оптические специальности или другие кафедры в этом цикле.
- Расширение на гуманитарные специальности (другой подход к faithfulness).

### Зона роста post-M6 (зафиксировано, не делаем сейчас)
- Cancel/stop генерации ответа в середине.
- Сохранение полезных ответов в избранное и личные заметки аспиранта.
- End-of-cycle обработка: что с данными аспиранта после сдачи кандэкзамена (архив / alumni / удаление).
- Cost visibility per tenant (трекинг расхода API per кафедра).
- Сравнение попыток self-check во времени (learning trend по теме).
- Временной срез / trend на дашборде научрука (динамика heatmap неделя к неделе).
- Supervisor как пользователь Q&A в режиме эксперта (отдельный mode).
- Cross-feature transitions (автоматическое предложение self-check после Q&A по той же теме).
- Удаление тенанта целиком (доступен только read-only).
- Prod-телеметрия / live-дашборд качества для super-admin.
- История Q&A-сессий аспиранта (возврат к старому диалогу).
- Несколько super-admin'ов на платформу (текущая модель — один).

> **Note:** onboarding научрука (first-time experience) **поднят из зоны роста в M5** — без него пилотный научрук залогинится и увидит «недостаточно данных», что = немедленный отток. См. BDD-сценарий 5.6.

### Out-of-scope по другим причинам
- Production SLA, multi-region, scale > 10 одновременных пользователей.
- Mobile-приложение.
- Disaster recovery, регулярные бэкапы.

---

## Changelog плана

- **v0.17 (2026-05-02)** — актуализация после потери worktree и восстановления документов из transcript. Зафиксированы 2 findings из real-world pre-M3 smoke (1 мая, до удаления worktree): (1) free-tier model availability не стабильна во времени — `qwen/qwen3-8b:free` отсутствует в OpenRouter каталоге; перед M3 нужно выбирать рабочую модель из актуального списка; (2) M2 verifier hard-gate не блокирует flow при `enough_evidence=False` — это расхождение с BDD 1.3, должно быть починено в M3.A.0 до first end-to-end run, иначе `refusal_correctness` (BDD 6.1) непредставима. Оба вынесены в риски M3 с явной митигацией.
- **v0.16 (2026-04-30)** — косметика: подзадачи M3 и M4 конвертированы из числовой схемы в буквенную (M3.1–M3.5 → M3.A–M3.E, M4.1–M4.4 → M4.A–M4.D) для единообразия с M5.A–M5.D и M6.A–M6.E. 16 cross-references обновлены. Note про collision на опциональном milestone Hybrid retrieval упрощено (исходная причина устранена). Параллельно — пост-факто bump bdd-scenarios.md до v0.6 для синхронизации с правкой в 4.6 от roadmap v0.8.
- **v0.15 (2026-04-30)** — финальная сверка roadmap'а на согласованность. (1) §3.1 актуализирован — Hetzner CX22 как зафиксированный hosting вместо «обсудить». (2) §3.2 дополнен production telemetry $5–10/мес. (3) §4 переоформлен в «открытые / закрытые»: Q7 (хостинг) и Q8 (privacy posture) перенесены в закрытые с указанием места решения; добавлены три ранее закрытые продуктовые развилки в ту же таблицу (topic-mode, concept-tagging, program-versioning). (4) §5 ссылка на BDD-сценарий 5.7 → 5.6 (после удаления concept confusions сценарии переnumbered). (5) Naming collision M3.5: милестоун «Hybrid retrieval» переименован в «Опциональный milestone — Hybrid retrieval (между M3 и M4)» без M-номера; все cross-references (§3.3 граф, §3.4 таблица, риски M3 и M4.5, M6 decisions framework) обновлены.
- **v0.14 (2026-04-30)** — критическая ревизия M6 на полноту. Закрыты 10 дыр: (1) migrations — manual `alembic upgrade head` до restart, не auto; (2) image-build через GitHub Actions, deploy — manual; (3) secret management — `.env` chmod 600 на VPS, копия в password manager, no-secrets-in-Sentry; (4) `daily_metrics_report.py` cron'ом для отслеживания просадки > 0.10; (5) privacy incident playbook (containment → assessment → notification → fix → post-mortem); (6) sampling алгоритм для LLM-judge в проде — каждый 10-й non-refused Q&A; (7) persona-level политика для разработчика — agg по умолчанию, persona только при incident response; (8) success criterion активности уточнён до «≥ 12 attempts за пилот»; (9) privacy incident определение — только confirmed leak, не blocked attempts; (10) reissue invite процесс описан; ответственный за DPIA-lite — tenant-admin или научрук. DoD расширен с 14 до 18 пунктов до запуска. Reactive support бound — 9–20 МСК.
- **v0.13 (2026-04-30)** — M6 углублён до подробного плана M6.A–M6.E. Зафиксированы: hosting (Hetzner CX22 €5–7/мес как baseline), deploy/backup/monitoring strategy для пилота, runbook требования, pre-flight checklist с 8 пунктами, последовательный onboarding (не пакетный) для smoke-теста consent-flow, weekly check-in cadence, mid+end surveys (5–7 вопросов), production-телеметрия с LLM-judge на ~10% sample (бюджет $5–10/мес), pilot-report 6-секционная структура, 5 binary success criteria, decisions framework на 4 категории. DoD на 14 пунктов в трёх временных гейтах (до/run/после). 7 рисков с митигацией.
- **v0.12 (2026-04-30)** — критическая ревизия M5 на полноту. Закрыты 5 дыр: (1) двойной gate heatmap (N_students ≥ 5 AND N_attempts ≥ 30, не только первое); (2) `qa_sessions.topic_id` добавлен в schema (был пропущен в M4.5, нужен для drilldown по refusal-reasons); (3) `self_check_attempts.status` enum зафиксирован явно (in_progress/completed/abandoned/invalid_evaluation); (4) Wilson CI считается в app-коде (не в SQL — PostgreSQL не имеет нативных функций); (5) onboarding покрывает 3 состояния включая «программа не загружена». Индексы для heatmap/drilldown queries добавлены. DoD расширен с 10 до 13 пунктов; DPIA-lite задача в governance явно зафиксирована.
- **v0.11 (2026-04-30)** — M5 углублён до подробного плана M5.A–M5.D + сквозная задача demo-data для onboarding. Зафиксированы: schema-additions (`users.supervisor_visibility`, `visibility_changed_at`, `tenants.config.analytics.min_aggregate_size`); aggregation queries с Wilson CI и явным учётом abandoned/soft-deleted; privacy middleware с 404 (не 403) при попытке доступа без opt-in; 4 типа audit-событий M5; UI-страницы с детерминированной анонимизацией (`Аспирант #N` через ROW_NUMBER); onboarding с реальной программой и синтетическими числами. DoD на 10 пунктов покрывает 8 BDD-сценариев. 5 рисков с митигацией.
- **v0.10 (2026-04-30)** — критическая ревизия M4.5 на полноту. Закрыты 11 дыр: ON DELETE policy для chunk_topics/program_topics/self_check_attempts (RESTRICT/CASCADE), backfill M2-материалов как первый шаг M4.5.C, required topics при загрузке material, триггер chunk_topics handle UPDATE/DELETE а не только INSERT, denormalized `program_topics.coverage_chunks` для O(1) coverage check, явная схема `tenants.config` (coverage.k_*, quality.low_quality_threshold), per-chunk override убран как overkill, калибровка quality-score threshold привязана к концу M4.5.C, eval-set v2 получает `topic_id`-аннотации и прогоняется в двух режимах (off/on), архивация programs — append-only без CASCADE; coverage_chunks counter учитывает только active материалы и пересчитывается при изменении `materials.status` (для корректности BDD 4.13). DoD расширен с 11 до 15 пунктов.
- **v0.9 (2026-04-30)** — M4.5 углублён до подробного плана M4.5.A–M4.5.E + сквозная задача topic-mode integration. Зафиксированы: формат `program.md` (markdown с фиксированной структурой H2/H3 + key_concepts), schema для programs/program_topics/material_topics/chunk_topics, bulk + LLM-helper flow для разметки источник→билет, формулы coverage (K=5 для self-check, K_qa=2 для Q&A), quality-score эвристика (3 компоненты, threshold 0.6), eval-set v2 с регрессионным сравнением. DoD на 11 пунктов покрывает 17 BDD-сценариев. 6 рисков с митигацией.
- **v0.8 (2026-04-30)** — ревизия M4 на полноту покрытия. Добавлено: `user_feedback` table (BDD 1.8), `materials.status` + `superseded_by` + `quality_score` (schema для BDD 4.13/4.7/4.8), soft-delete `users.deleted_at` + анонимизация attempts (BDD 7.3), `users.jwt_version` для role-revocation (BDD 7.5), tenant status transitions active↔read-only (BDD 8.3), explicit `default → optics-kafedra` handoff к M4.5, consent text storage (статика в репо), сквозная задача API surface с категориями endpoints, email-стратегия (queued в `outbound_emails`, SMTP отложен). Унифицирована роль `tenant-admin` (вместо `tenant-admin-co`) в BDD 4.6. DoD расширен с 9 до 15 пунктов; список покрываемых сценариев — 21 (operational 4.13 валидируется в M4.5).
- **v0.7 (2026-04-30)** — M4 углублён до подробного плана M4.1–M4.4: схема и миграция (DDL для tenants, добавление tenant_id в существующие таблицы, default-tenant + admin → super-admin); retrieval с tenant-фильтром через partial HNSW-индексы (с обоснованием почему не composite); RBAC matrix всех 4 ролей; invite-flow с таблицей `invite_codes`; bootstrap super-admin behavior; audit_log table; integration-тест cross-tenant изоляции для CI. Добавлен DoD-чек-лист на 9 пунктов и 4 риска с митигацией.
- **v0.6 (2026-04-30)** — закрыты три продуктовые развилки. **topic-mode** = hard toggle с асимметричным fallback (Q&A расширяет поиск, self-check блокируется). **concept-tagging** = пропуск в M5, перенос post-M6; M5 строится на per-bilet аналитике без concept-уровня. **program-versioning** = hard archive on replace + UX-разделение архивных attempts. Open question §9 удалён, M5 scope упрощён.
- **v0.5 (2026-04-30)** — ревизия по ролевым путешествиям. M5 расширен: first-time experience научрука и список аспирантов с opt-in добавлены IN-scope. Зона роста post-M6 пополнена 6 пунктами (трендовые сравнения, supervisor-as-expert, cross-feature transitions, удаление тенанта, live-телеметрия и др.). Onboarding научрука явно поднят из зоны роста в M5 как блокер пилота.
- **v0.4 (2026-04-30)** — зафиксировано позиционирование «обучающая среда, не аттестационная» в шапке. §5 (out-of-scope) разделён на 4 категории; явно перечислены апелляции/аттестация/proctoring как несовместимые с позиционированием; 5 зон роста post-M6 зафиксированы (cancel-генерации, избранное, onboarding научрука, end-of-cycle, cost visibility).
- **v0.3 (2026-04-30)** — введён платформенный принцип «multi-направления by design, single-направление by ship» (новый §1.4). M4 уточнён: tenant = направление, добавлен per-tenant конфиг-namespace. M4.5 переформулирован как референс-имплементация процесса. M3 углублён до подробного плана (M3.1–M3.5) с шаблонами JSONL, контрактом runner'а, формулами метрик, чек-листом готовности.
- **v0.2 (2026-04-30)** — публикационный трек (M7) удалён по решению автора. Единственная ось — кафедральный режим. Добавлен M4.5 (расширение корпуса до программы кафедры оптики). M3 переформулирован из «research foundation» в «инженерная страховка перед пилотом». Open questions переработаны под профиль кафедры оптики. Хостинг M6 поднят как явный блокер.
- **v0.1 (2026-04-30)** — первый драфт после обсуждения оценок защиты M2. Зафиксированы Оси A (кафедральный режим) и B (research artifact), milestones M3–M7, open questions для уточнения.
