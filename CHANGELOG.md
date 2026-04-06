# Changelog — ATLAS phd

Все значимые изменения проекта фиксируются в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/).
Версионирование по [SemVer](https://semver.org/lang/ru/): MAJOR.MINOR.PATCH.

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
