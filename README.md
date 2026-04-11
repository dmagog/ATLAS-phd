<p align="center">
  <img src="docs/branding/variants/atlas-icon-v5-shield-no-ring-calm-blue-inverted-preview-dark-1024.png" alt="ATLAS phd" width="120">
</p>

# ATLAS phd

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?logo=postgresql&logoColor=white)
![Status](https://img.shields.io/badge/Status-В%20разработке-blue)

**ATLAS (Assistant for Technical Learning & Attestation Support)** — агентный ассистент для подготовки к кандидатскому минимуму по технической специальности.

## Проблема

Подготовка к кандидатскому минимуму требует работы с большим объёмом разрозненных материалов (учебники, статьи, конспекты), а также регулярной самопроверки.

- Долго искать релевантные фрагменты вручную.
- Трудно проверять достоверность ответов и не «уходить» в галлюцинации.
- Нет быстрого цикла «изучил тему → проверил себя → получил обратную связь».

## Аудитория

- Аспиранты и соискатели по техническим направлениям.
- Пользователи, которым нужен ассистент по подготовке к техническому экзамену с опорой на источники и формулы.

## Агентный контур

MVP реализует детерминированный агентный конвейер поверх RAG:

1. **Retrieval** — поиск релевантных фрагментов из корпуса (pgvector, cosine similarity).
2. **Answer Node** — генерация ответа строго по найденным источникам, с inline-цитатами.
3. **Verifier** (hard-gate) — детерминированная проверка достаточности evidence и наличия цитат; при провале — одна попытка re-generation с расширенным контекстом.
4. **Self-check Generator** — RAG-заземлённая генерация вопросов (MC + открытые) по теме.
5. **Self-check Evaluator** — оценка ответов по рубрике (correctness 40% / completeness 30% / logic 20% / terminology 10%).

Маршрутизация по режимам (`Q&A` / `Self-check`) осуществляется на уровне API-эндпоинтов.

Подробнее: [`docs/specs/agent-orchestrator.md`](docs/specs/agent-orchestrator.md).

## Стек

| Слой | Технология |
|---|---|
| API / Web UI | FastAPI + Jinja2 |
| БД | PostgreSQL + pgvector (HNSW, cosine) |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, RU+EN, локально в Docker) |
| LLM | OpenRouter API (`qwen/qwen3-8b:free` по умолчанию) |
| Auth | JWT HS256, Argon2 пароли, RBAC (user / admin) |
| Ingestion | JSONL (page-aware) / PDF / DOCX / TXT / MD |
| Деплой | Docker Compose |

## Что MVP НЕ делает (out-of-scope)

- Не покрывает все дисциплины и форматы (например, `djvu`).
- Не обещает production-SLA и высокую нагрузку.
- Не заменяет преподавателя и не принимает экзаменационные решения.
- Не строит продвинутую долгосрочную learning-аналитику.
- Telegram-бот отложен за пределы текущего MVP.

## Документация

### Концепция и требования

| Документ | Описание |
|---|---|
| [Product Proposal](docs/product-proposal.md) | Проблема, аудитория, ценностное предложение, бизнес-метрики |
| [Техническое задание v1.1](docs/technical_specification.md) | Полный scope системы, функциональные и нефункциональные требования |
| [Матрица требований](docs/requirements.md) | Трассировка FR/NFR → Use Cases → приёмочные тесты |
| [Use Cases](docs/use_cases.md) | UC-01 (Q&A), UC-02 (Self-check), UC-03 (Ingestion), UC-04 (Auth) |
| [Plan приёмочных тестов](docs/acceptance_tests.md) | AT-01..AT-25: сценарии, шаги, критерии прохождения |
| [Governance](docs/governance.md) | Реестр рисков, политики логирования и конфиденциальности |

### Архитектура и реализация

| Документ | Описание |
|---|---|
| [System Design](docs/system-design.md) | PoC-архитектура: модули, контракты, защитные механизмы |
| [Оркестратор и промпты](docs/specs/agent-orchestrator.md) | Граф выполнения Q&A и Self-check, системные промпты LLM |
| [Retriever](docs/specs/retriever.md) | Гибридный поиск (vector + BM25/RRF), evidence gate |
| [Web & API](docs/specs/web-and-api.md) | Эндпоинты FastAPI, UI-страницы, схемы запросов/ответов |
| [Memory & Context](docs/specs/memory-and-context.md) | Сессионная память Q&A, управление контекстом |
| [Ingestion](docs/specs/ingestion.md) | Пайплайн загрузки: accept → extract → chunk → embed → index |
| [Observability & Evals](docs/specs/observability-and-evals.md) | Структурированные логи, KPI-метрики, eval-harness |
| [Serving & Config](docs/specs/serving-and-config.md) | Docker Compose, переменные окружения, секреты |

### Диаграммы

| Документ | Описание |
|---|---|
| [C4 Context](docs/diagrams/c4-context.md) | Границы системы и внешние акторы |
| [C4 Container](docs/diagrams/c4-container.md) | Контейнеры: app, postgres, embeddings |
| [C4 Component](docs/diagrams/c4-component.md) | Внутренние компоненты backend |
| [Workflow Graph](docs/diagrams/workflow-graph.md) | Граф выполнения запросов и ветви ошибок |
| [Data Flow](docs/diagrams/data-flow.md) | Движение данных через систему |

## Локальный запуск

### Требования

- Docker Desktop (или Docker Engine + Compose plugin)
- OpenRouter API key ([openrouter.ai](https://openrouter.ai))

> **Apple Silicon (M1/M2/M3):** все образы собираются под `linux/arm64` — дополнительных флагов не нужно. Первая сборка embeddings-сервиса займёт чуть дольше из-за компиляции torch для arm64.

### 1. Переменные окружения

```bash
cp .env.example .env
# Заполнить: LLM_API_KEY, ADMIN_EMAIL, ADMIN_PASSWORD, JWT_SECRET
```

`.env.example`:
```
LLM_API_KEY=your_openrouter_key_here
LLM_MODEL_ID=qwen/qwen3-8b:free

POSTGRES_PASSWORD=atlas_dev

JWT_SECRET=change_me_in_production
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=changeme

LOG_LEVEL=INFO
```

### 2. Запуск

```bash
docker compose up -d
```

Поднимаются три контейнера: `postgres` (pgvector), `embeddings` (sentence-transformers sidecar), `app` (FastAPI).

> **Первый запуск занимает 5–10 минут** — Docker собирает образы и embeddings-сервис скачивает модель `paraphrase-multilingual-MiniLM-L12-v2` (~100 МБ). При повторных запусках всё кэшировано и стартует за секунды.

При старте `app` автоматически применяет все Alembic-миграции и создаёт admin-пользователя из `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

### 3. Проверить готовность

```bash
docker compose logs -f app
```

Дождитесь строки `Application startup complete.` Это значит все три сервиса запущены.

### 4. Открыть интерфейс

```
http://127.0.0.1:8731
```

> Используйте `127.0.0.1`, а не `localhost` — некоторые сетевые конфигурации туннелируют `localhost` через внешний резолвер.

Войдите под `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

### 5. Загрузить учебные материалы

Репозиторий включает демо-корпус в папке `corpus/` — три учебника по оптике (Born & Wolf, Матвеев, Yariv). Для быстрого старта загрузите их одной командой:

```bash
ADMIN_EMAIL=<ваш_email> ADMIN_PASSWORD=<ваш_пароль> ./scripts/seed_corpus.sh
```

Или вручную через UI:
1. Перейти на страницу **Материалы** (шестерёнка в навигации).
2. Загрузить файлы (PDF / DOCX / TXT / MD / JSONL).
3. Дождаться завершения ingestion-job — прогресс виден на странице.

После загрузки система готова отвечать на вопросы, строить самопроверки и цитировать источники.

### 6. Smoke-check

Прогнать базовые сценарии из [`docs/acceptance_tests.md`](docs/acceptance_tests.md): `AT-01` (Q&A с цитатами), `AT-03` (отказ при отсутствии evidence), `AT-06` (самопроверка).

## Разработка (hot-reload)

Команда та же:

```bash
docker compose up -d
```

`src/` и `alembic/` монтируются как volume; uvicorn запущен с `--reload` — изменения кода подхватываются без пересборки образа.
