# Документация ATLAS phd

Эта папка содержит всю проектную документацию: от продуктового видения и
требований до дизайн-системы, специф архитектуры и операций пилота. Если
ты только что открыл репо — **start here**.

---

## 🚀 Первая остановка: что прочитать в зависимости от роли

### Аспирант / член комиссии (5 минут на ориентацию)

1. [`product-proposal.md`](product-proposal.md) — что за продукт, зачем, для кого
2. [`design/screenshots/after/README.md`](design/screenshots/after/README.md) — все ключевые экраны с тезисами
3. [`design/demo-script.md`](design/demo-script.md) — пошаговый сценарий повторной защиты

### Научрук / реальный пользователь-supervisor

1. [`welcome/supervisor.md`](welcome/supervisor.md) — onboarding для научрука
2. [`design/rationale.md`](design/rationale.md) §1.4 — privacy mask M5 (что видит / не видит)
3. [`pilot/pre-flight-checklist.md`](pilot/pre-flight-checklist.md) — что нужно от научрука перед стартом

### Tenant-admin / разворачивающий пилот

1. [`welcome/tenant-admin.md`](welcome/tenant-admin.md) — onboarding для админа кафедры
2. [`deployment/local-pilot.md`](deployment/local-pilot.md) — локальный запуск через docker-compose
3. [`runbook.md`](runbook.md) — операционные процедуры (бэкапы, восстановление, мониторинг)

### Разработчик / контрибьютор

1. [`system-design.md`](system-design.md) — обзор PoC-архитектуры
2. [`specs/agent-orchestrator.md`](specs/agent-orchestrator.md) — главный конвейер
3. [`design/design-system.md`](design/design-system.md) — токены и компоненты UI
4. [`bdd-scenarios.md`](bdd-scenarios.md) — Gherkin-сценарии (что должно работать)

### Защита диссертации (готовый комплект)

1. [`design/screenshots/after/README.md`](design/screenshots/after/README.md) — gallery с тезисами для слайдов
2. [`design/demo-script.md`](design/demo-script.md) — что говорить и в каком порядке
3. [`design/demo-recording-protocol.md`](design/demo-recording-protocol.md) — как снять fallback-GIF
4. [`design/rationale.md`](design/rationale.md) — обоснование UX-решений в академических терминах

---

## 📂 Структура папки

### `*.md` (top-level) — концепция, ТЗ, ассеты

| Файл | О чём |
|---|---|
| [`product-proposal.md`](product-proposal.md) | Проблема, аудитория, ценность, бизнес-метрики |
| [`technical_specification.md`](technical_specification.md) | Полное ТЗ v1.1 — функциональные и нефункциональные требования |
| [`requirements.md`](requirements.md) | Матрица FR/NFR → Use Cases → приёмочные тесты |
| [`use_cases.md`](use_cases.md) | UC-01 (Q&A), UC-02 (Self-check), UC-03 (Ingestion), UC-04 (Auth) |
| [`acceptance_tests.md`](acceptance_tests.md) | AT-01..25: сценарии, шаги, критерии прохождения |
| [`bdd-scenarios.md`](bdd-scenarios.md) | 53 Gherkin-сценария по 8 фичам, мапинг на milestones |
| [`governance.md`](governance.md) | Реестр рисков, политики логирования и privacy |
| [`roadmap.md`](roadmap.md) | M3-M6 milestones (eval harness → multi-tenant → supervisor → пилот) |
| [`design-roadmap.md`](design-roadmap.md) | UI/UX роадмап (Phase 1-6: audit → design system → wireframes → реализация → demo packaging) |
| [`system-design.md`](system-design.md) | PoC-архитектура: модули, контракты, защитные механизмы |
| [`runbook.md`](runbook.md) | Операционный runbook: бэкап БД, restore, ingest нового материала, миграции, etc |

### `specs/` — спецификации модулей

| Файл | Что описывает |
|---|---|
| [`specs/agent-orchestrator.md`](specs/agent-orchestrator.md) | Главный конвейер: planner → retrieval → answer → verifier; промпты LLM |
| [`specs/retriever.md`](specs/retriever.md) | Гибридный поиск (vector + BM25 + RRF), evidence-gate |
| [`specs/ingestion.md`](specs/ingestion.md) | Pipeline загрузки: accept → extract → chunk → embed → index |
| [`specs/memory-and-context.md`](specs/memory-and-context.md) | Сессионная память Q&A, управление контекстом |
| [`specs/observability-and-evals.md`](specs/observability-and-evals.md) | Структурированные логи, KPI-метрики, eval-harness |
| [`specs/serving-and-config.md`](specs/serving-and-config.md) | Docker Compose, переменные окружения, секреты |
| [`specs/tools-and-apis.md`](specs/tools-and-apis.md) | Внешние интеграции (OpenRouter LLM, embeddings sidecar) |
| [`specs/web-and-api.md`](specs/web-and-api.md) | FastAPI-эндпоинты, Jinja2-страницы, схемы запросов/ответов |

### `diagrams/` — архитектурные диаграммы

| Файл | Уровень |
|---|---|
| [`diagrams/c4-context.md`](diagrams/c4-context.md) | C4 Context — границы системы и внешние акторы |
| [`diagrams/c4-container.md`](diagrams/c4-container.md) | C4 Container — контейнеры (app, postgres, embeddings) |
| [`diagrams/c4-component.md`](diagrams/c4-component.md) | C4 Component — внутренние компоненты backend |
| [`diagrams/workflow-graph.md`](diagrams/workflow-graph.md) | Граф выполнения запросов и ветви ошибок |
| [`diagrams/data-flow.md`](diagrams/data-flow.md) | Движение данных через систему |

Все диаграммы в Mermaid + side-by-side SVG-рендер.

### `design/` — UI/UX

| Файл | Phase | О чём |
|---|---|---|
| [`design/ux-audit.md`](design/ux-audit.md) | 1 | Аудит «before»: что есть, что слабо, что отсутствует. Карта существующих экранов |
| [`design/competitive-scan.md`](design/competitive-scan.md) | 1 | Бенчмарк (NotebookLM / Perplexity / Linear / Vercel) под P0-экраны |
| [`design/wireframes.md`](design/wireframes.md) | 3 | Structural drafts ключевых экранов на дизайн-системе |
| [`design/design-system.md`](design/design-system.md) | 2 | Токены (palette, typography, spacing) + 18 компонентов; обоснование выбора стека |
| [`design/rationale.md`](design/rationale.md) | 6 | Обоснование UX-решений в академических терминах (Nielsen / WCAG / Floridi). **Раздаточный материал для комиссии.** |
| [`design/demo-script.md`](design/demo-script.md) | 1 → 6 | Сценарий защиты: 7 шагов на 6 минут, тезисы, **inline-скриншоты** |
| [`design/demo-recording-protocol.md`](design/demo-recording-protocol.md) | 6 | Как снять fallback-GIF screencast'а (на случай LLM-downtime) |
| [`design/screenshots/after/README.md`](design/screenshots/after/README.md) | 6 | **Walkthrough всех экранов** с тезисом + demo-сценарием. Главная gallery. |
| [`design/screenshot-gallery.md`](design/screenshot-gallery.md) | 1 | Deprecated → редирект на `screenshots/after/README.md` |

Папки внутри `design/`:
- [`design/screenshots/after/`](design/screenshots/after/) — 14 PNG актуальных скриншотов (login → chat → source-modal → refusal → selfcheck старт/зачёт/не-зачёт → supervisor → tenant-admin → eval → tenants → invites → semicon proof)
- [`design/screencasts/`](design/screencasts/) — пустая, для GIF'ов после съёмки

### `welcome/` — onboarding-материалы для разных ролей

| Файл | Для кого |
|---|---|
| [`welcome/student.md`](welcome/student.md) | Студент: как залогиниться, как работать с чатом и self-check |
| [`welcome/supervisor.md`](welcome/supervisor.md) | Научрук: как читать heatmap, что показывает privacy mask |
| [`welcome/tenant-admin.md`](welcome/tenant-admin.md) | Админ кафедры: как управлять программой, инвайтами, материалами |

### `deployment/` — инфраструктура

| Файл | О чём |
|---|---|
| [`deployment/local-pilot.md`](deployment/local-pilot.md) | Локальный запуск через docker-compose (single-machine pilot) |
| [`deployment/hetzner-setup.md`](deployment/hetzner-setup.md) | Production-deploy на Hetzner VM |

### `pilot/` — операционные процедуры пилота

| Файл | Когда использовать |
|---|---|
| [`pilot/pre-flight-checklist.md`](pilot/pre-flight-checklist.md) | Перед запуском: проверка окружения, seed, верификация |
| [`pilot/timeline.md`](pilot/timeline.md) | Расписание пилота, ключевые даты, ответственные |
| [`pilot/weekly-checkin-template.md`](pilot/weekly-checkin-template.md) | Шаблон еженедельного отчёта |
| [`pilot/incident-runbook.md`](pilot/incident-runbook.md) | Что делать при инциденте (LLM down, БД, security, etc) |
| [`pilot/end-of-pilot-report-template.md`](pilot/end-of-pilot-report-template.md) | Шаблон финального отчёта пилота |

### `branding/` — бренд-ассеты

- [`branding/atlas-icon.svg`](branding/atlas-icon.svg) + PNG-вариант
- [`branding/atlas-icon-detailed.svg`](branding/atlas-icon-detailed.svg) + PNG-вариант
- [`branding/variants/`](branding/variants/) — 14 вариантов иконки (calm-blue / deep-teal / mono / inverted / shield-no-ring / book / evidence)

В production используется `atlas-icon-v5-shield-no-ring-calm-blue.svg`.

---

## 🗺️ По стадиям разработки

| Стадия | Статус | Документы |
|---|---|---|
| **Концепция** | ✅ зафиксировано | product-proposal, technical_specification, use_cases |
| **Требования + тесты** | ✅ зафиксировано | requirements, acceptance_tests, bdd-scenarios, governance |
| **Архитектура** | ✅ зафиксировано | system-design, specs/, diagrams/ |
| **M2 PoC** | ✅ работает | (исторически в первых коммитах) |
| **M3 Eval-harness** | ✅ работает | roadmap §M3, eval/run_eval.py + результаты в eval/results/ |
| **M4 Multi-tenant** | ✅ работает | roadmap §M4.A-C |
| **M4.5 Программа кафедры** | ✅ работает | roadmap §M4.5 |
| **M5 Supervisor mode** | ✅ работает | roadmap §M5 |
| **M6 Пилот** | 🟡 готовы операционные документы | pilot/, deployment/ |
| **Phase 1-2 UI audit + design system** | ✅ готово | design/ux-audit, design/design-system |
| **Phase 3-5 wireframes → реализация** | ✅ готово | design/wireframes, web/templates/ |
| **Phase 6 demo packaging** | ✅ готово | design/demo-script + screenshots/after/ + scripts/seed_demo.sh |

---

## 🎯 Главные цифры (для quick-look)

Полные метрики и их аннотация — в [`design/screenshots/after/README.md`](design/screenshots/after/README.md) Шаг 6.

| Метрика | Значение | Откуда |
|---|---|---|
| **`refusal_tnr`** | **1.000** vs baseline 0.000 | M3 eval-set v1.1, 20 off-topic вопросов |
| **`κ_binarized`** | **1.000** | M3.A self-check rubric vs expert (бинарная классификация) |
| **Hard-gate latency p95** | **< 2 s** | retrieval-уровень, без LLM-вызова |
| Воспроизводимость | 7/7 совпадений refusal-исходов | 7 повторных прогонов eval-set'а |
| Корпус (пилот) | **17 807 чанков** в 3 учебниках | optics-kafedra, Born&Wolf + Матвеев + Yariv |
| Покрытие программы | **100%** зелёных топиков | 6/6 топиков с coverage ≥ K_qa |

---

## 📜 Changelog документации

- **2026-05-08:** добавлен этот TOC + реструктура `screenshots/after/README.md` в walkthrough-формат + 9 inline screenshots в `demo-script.md`.
- **2026-05-07:** Phase 6 — `screenshots/after/`, `demo-recording-protocol.md`, `rationale.md`, gallery.
- **2026-05-07:** Phase 1-3 — `ux-audit`, `competitive-scan`, `demo-script`, `wireframes`, `design-system`, `design-roadmap`.
- **2026-05 ранее:** концепция, ТЗ, спецификации, диаграммы, roadmap M3-M6, runbook.
