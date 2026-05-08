# Release v0.8.0 — Production UI + Demo packaging

**Дата:** 2026-05-09
**Состояние:** ATLAS phd готов к **повторной защите**: production-grade UI, дизайн-система из 18 BEM-компонентов, полный walkthrough из 10 аннотированных скриншотов, one-command demo-стенд с 14 пользователями и 92 self-check attempts.

---

## TL;DR

| Domain | Status |
|---|---|
| **Phase 1 — UX audit** | ✅ Гэп-анализ всех экранов, 4 ключевых проблемы выявлены |
| **Phase 2 — Дизайн-система** | ✅ `atlas.css` (~600 строк), 18 BEM-компонентов, light + dark, brand-цвета из SVG |
| **Phase 3 — Wireframes** | ✅ 9 wireframe-файлов как visual reference (отгружены в Phase 5) |
| **Phase 4 — Polish** | ✅ Motion, focus-state, sticky topbar/sidebar, responsive bar-cmp |
| **Phase 5 — Production UI** | ✅ Полная переписка под `_app.html` + `_partials.html`, source-modal, eval-dashboard, supervisor heatmap, tenant-admin, citation pills |
| **Phase 6 — Demo packaging** | ✅ `seed_demo.sh` one-command, 14 demo-users, ~40 hand-crafted + 12 real LLM attempts, 3 showcase, walkthrough из 10 PNG |

---

## Главные результаты для защиты

> **Эти три цифры — главные результаты диссертации.** Все badges в README ведут на их источники.

| Метрика | Значение | Что означает |
|---|---|---|
| `refusal_tnr` | **1.000** (vs baseline 0.000) | True negative rate на off-topic вопросах. 100/100 «вне корпуса» отказов в treatment, 0/100 в baseline. |
| `κ_binarized` | **1.000** | Cohen's κ на бинарной классификации зачёт/незачёт между self-check рубрикой и экспертной разметкой. Perfect agreement. |
| Hard-gate p95 | **<2s** | Отказ принимается на retrieval-уровне без вызова LLM. Не зависит от провайдера, не тратит токены. |

См. [`docs/design/screenshots/after/08-eval-dashboard.png`](docs/design/screenshots/after/08-eval-dashboard.png) и [`eval/results/M3-report.md`](eval/results/M3-report.md).

---

## Что входит в этот release (с момента 0.7.0)

Полный список — в [`CHANGELOG.md`](CHANGELOG.md) §0.8.0. Кратко:

### Production UI (Phase 5)

- **Новый base layout** `_app.html` + `_partials.html` со sidebar/topbar и auth-bootstrap JS, replacing legacy `base.html` с in-app login modal.
- **`/login`** — отдельная страница с brand-side + form-side, invite-code flow, защита от open-redirect в `?next=`.
- **`/eval`** — новый dashboard для super-admin: 3 hero-cards (refusal_tnr / κ / latency p95) + per-topic table + reproducibility + history. Читает реальные результаты из `eval/results/*` через `eval.py` router.
- **Чат `/`** переписан с inline citation pills `[N]` (вместо tail-list `[Doc:..., p.N]`), source-panel с дедупликацией, hard-gate verified badge на русском, refusal-state как first-class экран.
- **Source-modal** — клик по `[N]` или source-card открывает full snippet с KaTeX-рендером формул.
- **Self-check `/self-check`** — hero score + rubric grid с явными весами 40/30/20/10 + per-question breakdown.
- **Supervisor `/supervisor`** — per-topic aggregates + students с privacy mask M5 (opted-in vs «Аспирант #N»).
- **Tenant-admin `/tenant-admin`** — программа кафедры с bar-fill покрытия, инвайты, пользователи.
- **`/_/tenants` + `/_/invites`** — кросс-тенантный list для super-admin и dedicated invites view для tenant-admin.

### Дизайн-система (Phase 2 + 4)

- **`src/atlas/static/atlas.css`** (~600 строк) — токен-набор (light + dark) + 18 BEM компонентов + ~30 utility-классов.
- **Brand-цвета** извлечены из SVG `atlas-icon-v5-shield-no-ring-calm-blue`: `#1D4ED8` (calm-blue), `#1E293B` (slate).
- **`/_/styleguide`** — live-демо всех компонентов с theme-toggle.
- Phase 4 polish: motion (stagger entrance, refusal scale-in, pulse-ring badge), focus-state на dark, bar-cmp responsive, heatmap data-tip, light-mode shadows, sticky topbar/sidebar.

### Demo packaging (Phase 6)

- **`scripts/seed_demo.sh`** — orchestrator one-command: docker up → seed users → seed attempts → smoke verify.
- **`scripts/seed_demo_users.py`** — 14 demo-пользователей (1 super + 1 tenant-admin + 1 supervisor + 12 студентов с русскими именами + privacy mask 7 visible / 5 anonymous).
- **`scripts/seed_demo_attempts.py`** — ~40 hand-crafted self-check attempts с реалистичным распределением scores.
- **`scripts/seed_demo_real_attempts.py`** — 12 real LLM self-check сессий (по одной на студента) для drill-down comissia-proof данных.
- **`scripts/seed_demo_showcase.py`** — 3 «звёздные» attempts (4.5+) для ivanov как best-student kasus.
- **`scripts/demo_questions.json` + `verify_demo_questions.py`** — курированный список Q&A + refusal questions с pre-defense smoke test.
- **`/_/demo-login` + `/_/logout`** helper routes — instant-login для @optics.demo accounts (404 в production).
- **`?ask=` + `?open-source=` + `?open=` URL params** на chat/history для воспроизводимых screenshot-flow.

### Документация и иллюстрации

- **`docs/README.md`** — TOC + reading paths для 5 аудиторий.
- **`docs/design/screenshots/after/`** — 10 PNG скриншотов (login → chat → source-modal → refusal → selfcheck → supervisor → tenant-admin → eval → tenants → invites) с walkthrough README, тезисами и demo-сценариями.
- **`docs/design/demo-script.md`** обновлён — 9 inline screenshots по шагам.
- **`docs/welcome/{student,supervisor,tenant-admin}.md`** проиллюстрированы.
- **`docs/system-design.md`** — embed C4 SVG диаграмм (context / container / workflow).
- **`docs/deployment/local-pilot.md`** — success-state screenshot после health-check.
- **`docs/design/{ux-audit,competitive-scan,wireframes,design-system,rationale,demo-script,demo-recording-protocol}.md`** — полный дизайн-track Phase 1–6.
- Топ-уровневый **`README.md`** переработан: hero metrics в badges, 3-image showcase grid, quick-start через `seed_demo.sh`, demo-аккаунты таблицей.

### Удалено (Phase 5.7)

- `templates/base.html` (legacy с in-app login modal), `templates/index.html` (legacy `/qa`), `templates/wf/*` (9 wireframe-файлов; перенесены в production templates), web-route `GET /qa`.

---

## Запуск demo-стенда

```bash
cp .env.example .env
# Заполнить: LLM_API_KEY (OpenRouter), JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD

./scripts/seed_demo.sh
```

После завершения откройте `http://127.0.0.1:8731/login` и выберите роль (student / supervisor / tenant-admin / super-admin) с паролем `demo`. Все 4 роли документированы в [`README.md`](README.md#-быстрый-старт-одна-команда) и [`docs/welcome/`](docs/welcome/).

---

## Что дальше

Roadmap M6.B/C — реальный пилот с 3–5 аспирантами на кафедре оптики:
- [`docs/deployment/local-pilot.md`](docs/deployment/local-pilot.md) — friend-пилот на ноутбуке через Tailscale/LAN/Cloudflare.
- [`docs/deployment/hetzner-setup.md`](docs/deployment/hetzner-setup.md) — production VPS deploy.
- [`docs/pilot/timeline.md`](docs/pilot/timeline.md) + [`docs/pilot/incident-runbook.md`](docs/pilot/incident-runbook.md) — операционные runbook'и.

Архитектурные горизонты — `docs/roadmap.md` М5/М6 (advanced learning analytics, telegram-бот, multi-kafedra onboarding).
