# UX Audit — стартовая точка перед редизайном

> **Версия:** 0.1 (2026-05-07)
> **Метод:** code-only audit. Скриншоты «до» сняты не были (блокер Chrome-расширения, см. журнал сессии). Скриншоты «после» снимем в Фазе 6 — для защиты важна именно галерея «после».
> **Контекст:** [`docs/design-roadmap.md`](../design-roadmap.md) Фаза 1.

---

## 1. Карта существующего UI

### 1.1 Web-страницы (всё, что есть)

Из [`src/atlas/api/routers/web.py`](../../src/atlas/api/routers/web.py):

| Маршрут | Шаблон | Назначение |
|---|---|---|
| `/` | `chat.html` | Универсальный чат (Q&A + Self-check через planner) |
| `/qa` | `index.html` | Старый Q&A-only экран (до появления чата) |
| `/self-check` | `selfcheck.html` | Самопроверка с явным вводом темы |
| `/self-check/history` | `history.html` | История попыток самопроверки |
| `/admin` | `admin.html` | Загрузка материалов + список документов |

**Всего: 5 web-страниц.**

### 1.2 API-роуты без UI

Из [`src/atlas/api/routers/`](../../src/atlas/api/routers/):

| Роутер | Что предоставляет | Web-страница? |
|---|---|---|
| `supervisor.py` | `heatmap`, `students` (ключевые M5-данные) | **нет** |
| `tenants.py` | CRUD тенантов, `program`, `coverage` | **нет** |
| `invites.py` | Создание/redeem инвайт-кодов | **нет** |
| `me.py` | Профиль, visibility-настройки студента | **нет** |
| `auth.py` | Login / refresh / logout | **нет** (только модалка в `base.html`) |

**Это критическая находка:** функциональный backend M4–M5 (multi-tenancy, supervisor dashboard, invite-flow, программа кафедры, корпус-coverage) реализован, **но web-UI для всех этих сценариев отсутствует**. Существующие 5 страниц закрывают только M2-уровень (Q&A + Self-check + ingestion).

### 1.3 Внешние артефакты

- **Eval-harness** — CLI-скрипты в `eval/run_eval.py`, `eval/score.py`. Нет web-дашборда. Цифры M3 (`refusal_tnr 1.000 vs 0.000`, `κ_binarized = 1.000`) живут в логах/JSON, не имеют визуального носителя в продукте.
- **Branding** — в [`docs/branding/variants/`](../branding/variants/) есть готовые SVG/PNG в нескольких вариантах: `v5-shield-no-ring-calm-blue`, `-deep-teal`, `-mono`, `-inverted`. Богатый набор, но в продукте используется только `static/logo.png` (старый PNG, не совпадает с актуальной серией).

---

## 2. Дизайн-система: что есть сейчас

Из [`src/atlas/templates/base.html`](../../src/atlas/templates/base.html) `<style>`-блок (~30 строк inline-CSS):

### 2.1 Палитра

| Назначение | Цвет | Источник |
|---|---|---|
| Фон body | `#f5f5f5` | inline |
| Фон card | `#fff` | inline |
| Текст основной | `#1a1a1a` | inline |
| Текст вторичный | `#6b7280` (Tailwind gray-500) | inline в каждом шаблоне |
| Header background | `#1a1a2e` (тёмно-синий) | inline |
| Nav link | `#a0b4d0` | inline |
| Primary button | `#2563eb` (Tailwind blue-600) | inline |
| Admin nav link | `#fbbf24` (Tailwind amber-400) — выделяет admin-только | inline |
| Error | `#dc2626` (Tailwind red-600) | inline |
| Success / score-high | `#16a34a` (Tailwind green-600) | inline |
| Warning / score-mid | `#d97706` (Tailwind amber-600) | inline |
| Tag bg / Q&A user msg bg | `#dbeafe` / `#eff6ff` | inline |

**Наблюдение:** палитра уже de-facto Tailwind-совместимая (используются те же оттенки), но без какого-либо токенизирования. Нет CSS-переменных, нет dark mode, бренд-цвет «calm-blue» из [`branding/`](../branding/) в коде не используется.

### 2.2 Типографика

- Один стек: `system-ui, -apple-system, sans-serif`
- Размеры заданы прямо в шаблонах через `font-size: .85rem / .9rem / 1rem / 1.1rem / 1.4rem / 2rem ...` без шкалы.
- Моноширинный шрифт для кода: только дефолтный браузерный `<code>` со светло-серым фоном.
- Формулы: KaTeX (CDN), рендерится через `auto-render`.

### 2.3 Компоненты

В [`base.html`](../../src/atlas/templates/base.html):

| Компонент | Реализация | Состояние |
|---|---|---|
| `header` + `nav` | inline | Тёмный, плоский, кликабельный |
| `.container` | `max-width: 860px` | **Слишком узкий** для дашбордов |
| `.card` | `border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.08)` | OK |
| `input / textarea / select` | inline | Базовое оформление |
| `.btn-primary / .btn-secondary` | inline | OK |
| `.tag` | inline | Используется для citation-chip |
| `.fb-btn` (feedback) | inline | thumbs up/down |
| Login modal (`#login-overlay`) | inline в `base.html` | **Не отдельная страница**, а полупрозрачная подложка |
| Loading spinners | inline в каждом шаблоне | Дублируется (`@keyframes spin` определён в `chat.html` и `selfcheck.html` отдельно) |
| Step badges | inline в `selfcheck.html` | Шаги pipeline: «Анализирую тему» → «Составляю вопросы» → «Финализирую» |

**Дублирование:** одинаковые keyframes/стили скопированы между шаблонами. Нет единого `static/atlas.css`.

### 2.4 Иконография

Bootstrap Icons через CDN (`<link href="cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3">`). Используются: `bi-chat-dots-fill`, `bi-question-circle`, `bi-card-checklist`, `bi-clock-history`, `bi-gear-fill`, `bi-shield-check`, `bi-check-circle-fill`, `bi-x-circle-fill`, `bi-search`, `bi-pencil`, `bi-book-half`, `bi-crosshair`, `bi-list-check`, `bi-cpu`, `bi-bar-chart-line`, `bi-lightbulb`, `bi-hash`, `bi-database`, `bi-scissors`, `bi-arrow-clockwise`, `bi-hand-thumbs-up/down`.

Иконки бренда из [`branding/variants/`](../branding/variants/) — **не используются**.

---

## 3. Постранично: что есть, что сломано, что отсутствует

### 3.1 `/` — Чат ([chat.html](../../src/atlas/templates/chat.html))

**Что есть:**
- Profile selector (Подробный / Краткий / Учебный)
- Language selector (RU / EN)
- Planner-badge (`→ Q&A` / `→ Самопроверка` / `→ Уточнение`) — отображается на 4 секунды после ответа
- Сообщения с alignment user-right / atlas-left
- Typing indicator с rotating steps (`Планирую запрос...` → `Ищу в материалах...` → `Формирую ответ...` → `Проверяю точность...`)
- Citation chips после ответа (`<span class="tag">Born&Wolf, с.42</span>`)
- Feedback thumbs up/down с `request_id`
- Inline self-check quiz карточки прямо в чате
- Session memory через `sessionStorage`
- Кнопка `Очистить`

**Что слабо/неочевидно:**
- Контейнер `860px` — узко для длинных ответов и для дашборд-режима.
- Refusal-кейс: красный текст в той же серой пузырьковой карточке. **Никак не выделяется как «защитный механизм»** — для комиссии невидимо, что hard-gate сработал.
- Hard-gate badge отсутствует — вообще нет визуального indicator'а, что верификатор активен.
- Источники — только текст «Born&Wolf, с.42», нет drill-down (нельзя открыть страницу/контекст).
- Citation-chip и tag — один компонент с разной семантикой; визуально не отличаются.
- Planner-badge виден всего 4 секунды — слишком быстро, легко пропустить во время демо.

**Что отсутствует:**
- Suggested questions (промо-режим / onboarding).
- Visualization источников (текущий чанк, similarity score).
- «Verified by retrieval gate» badge для каждого ответа.
- Кнопка «Воспроизвести» (для демо: повторить тот же запрос).

### 3.2 `/qa` — Старый Q&A ([index.html](../../src/atlas/templates/index.html))

**Состояние:** legacy. Дублирует часть функционала `/`, но без planner-routing, без self-check, без typing-steps. Назначение в текущей архитектуре неясно.

**Решение:** удалить из IA или скрыть из навигации. Текущий пункт меню `Q&A` ведёт сюда — это путаница.

### 3.3 `/self-check` — Самопроверка ([selfcheck.html](../../src/atlas/templates/selfcheck.html))

**Что есть (сильное):**
- Step badges с прогрессом (анимированные пилюли: `активна → done`)
- Score-bar с цветовой градацией (`#16a34a` / `#d97706` / `#dc2626`)
- 4-cell criterion grid (Точность 40% / Полнота 30% / Логика 20% / Терминология 10%) — **уже визуализирует рубрику**
- Per-question breakdown с иконкой статуса, подсветкой правильного ответа, зачёркиванием неверного
- Error tags
- Evaluator summary с цветной полоской слева

**Что слабо:**
- Карточка результата — длинный вертикальный список без явной hero-зоны. Для скриншота получается «полотно», а не «кадр».
- Score «4.2 / 5» подаётся как текст, без сравнительного контекста (распределение по студентам, динамика).
- Verdict («Отлично» / «Хорошо» / ...) в маленьком шрифте рядом — легко пропускается.

**Что отсутствует:**
- Сравнение с эталонным экспертом (κ_binarized = 1.000 — это центральная цифра M3 для self-check, и нет ни одного места, где она показывается).
- Drill-down: какие именно цитаты использовались для оценки.
- Возможность повторить попытку по той же теме / экспортировать результат.

### 3.4 `/self-check/history` — История ([history.html](../../src/atlas/templates/history.html))

**Что есть:** список попыток с score-badge, status pill (`В процессе` / `Отправлено` / `Оценено` / `Ошибка`), модалка деталей.

**Что слабо:**
- Нет фильтров по дате / теме / score.
- Нет агрегатов («средний score за неделю», «топ-3 темы по падению»).
- Модалка деталей — полная копия страницы результатов, а не отдельный design.

**Что отсутствует:**
- Группировка по топикам программы (это требует supervisor-flow, но и студенту полезно).
- Экспорт.
- Сравнение двух попыток по одной теме («прогресс»).

### 3.5 `/admin` — Материалы ([admin.html](../../src/atlas/templates/admin.html))

**Что есть (сильное):**
- Indeterminate progress bar с CSS-анимацией
- Pipeline stage label (`extract → chunk → embed → index`) с иконками
- Принято / отклонено — две раздельные группы с reason labels
- Таблица документов (Название / Файл / Чанков / Загружен)

**Что слабо:**
- `<input type="file">` — дефолтный браузерный, не drag-and-drop, не показывает превью.
- Таблица документов плоская; нет статуса (active / archived), нет поиска, нет действий (re-ingest, delete).
- Cron / периодический ingestion не отражён в UI.

**Что отсутствует:**
- Visualization corpus coverage (`tenants.py:/{slug}/coverage` существует, но не визуализирован).
- Программа кафедры (`tenants.py:/{slug}/program`) — UI отсутствует.
- Связка «топик программы → материалы, покрывающие этот топик» — отсутствует.

### 3.6 Login overlay (внутри [base.html](../../src/atlas/templates/base.html))

**Что есть:** полупрозрачная подложка + центр-карточка с email/password.

**Что слабо:**
- Нет separate page `/login`. Любая deep-link навигация показывает сначала контент за подложкой (моргание), потом overlay.
- Нет логотипа на login.
- Нет сообщения «нет аккаунта? используйте инвайт-код» (M4.A invite-flow есть, login его не упоминает).
- Нет «забыли пароль» (out-of-scope, но визуально отсутствует — оставит ощущение «недоделано»).

### 3.7 Header + nav ([base.html](../../src/atlas/templates/base.html))

**Что есть:** один ряд: `[logo] ATLAS phd  [nav: Чат|Q&A|Самопроверка|История|Материалы]  [email + Выйти]`.

**Что слабо:**
- Один и тот же nav для всех ролей. Студент видит «Материалы» (но получит 403 при клике, если нет прав). Tenant context не показан (для какого тенанта залогинен?).
- Нет switching tenant для super-admin.
- Нет role badge (super-admin / tenant-admin / supervisor / student).

**Что отсутствует:**
- Supervisor-навигация: студенты, heatmap, программа.
- Tenant-admin-навигация: пользователи, инвайты, программа, материалы.
- Super-admin-навигация: список тенантов, аудит-лог, eval-дашборд.

### 3.8 Refusal как UX-сценарий

**Текущая реализация (chat.html:162):**
```js
const msg = data.refusal_message || 'Не удалось получить ответ.';
appendMsg('msg-atlas', 'ATLAS', `<span style="color:#dc2626">${mdToHtml(msg)}</span>`);
```

Красный `<span>` в обычной серой пузырьковой карточке. **Невидимо**, что произошёл retrieval hard-gate с обоснованием. Для защиты диссертации это **самое слабое место**: ключевой результат M3.A (`refusal_tnr 1.000 vs 0.000`) реализован в коде, но не показан в UI.

---

## 4. Доступность и плотность

- Контраст: header `#1a1a2e` ↔ `#a0b4d0` — ~4.4:1, на грани AA для normal text. nav-text 0.9rem (~14px) — всё ещё OK, но margin минимальный.
- Контраст amber-400 admin-link на dark navy — низкий.
- Aria-labels: отсутствуют для иконочных кнопок (feedback thumbs).
- Keyboard nav: работает (HTML-форма, button), но focus-styles браузерные (синяя рамка).
- Нет skip-links.
- Шрифт 0.85–0.92rem — на проекторе мелковато.

---

## 5. Сводка приоритетов перед Фазой 2

### 5.1 Что добавить (P0, без чего нельзя выйти на защиту)

1. **Refusal как first-class screen** — отдельная карточка с иконкой щита, объяснением, evidence-метриками, badge «Hard-gate сработал».
2. **`/eval` дашборд** — визуализация baseline vs verifier с per-topic breakdown. Носитель центральной цифры M3.
3. **Hero-cards для self-check результата** — большой score + verdict + sparkline / сравнение, не плотная таблица.
4. **Supervisor dashboard** — heatmap студент×топик уже есть в API (`/{slug}/supervisor/heatmap`), нужен UI.
5. **Tenant context + role badge в header** — без этого demo «multi-tenancy» неубедительно.
6. **Login как отдельная страница** с логотипом из [`branding/`](../branding/) и упоминанием инвайт-флоу.

### 5.2 Что переделать (P1)

7. **Удалить или скрыть `/qa`** — legacy, путает с чатом.
8. **Расширить контейнер** до ~1200px на дашбордах; `/` оставить узким для чата.
9. **Унифицировать spinners / steps / tag-стили** в один `static/atlas.css` с CSS-переменными.
10. **Citation-chip** сделать кликабельной: показывать чанк / similarity score / страницу.
11. **Materials**: drag-and-drop, статус документа, связь с программой.

### 5.3 Что добавить как новые экраны (P1)

12. **Supervisor: students list, student drill-down, program coverage**.
13. **Tenant-admin: invite management, users list, program editor**.
14. **Super-admin: tenants list, audit-log viewer**.
15. **Onboarding via invite-code** (отдельный flow, отличный от login).
16. **Settings / Profile** (visibility-настройки M5 уже в API).

### 5.4 Что отложить (P2)

17. Drag-and-drop reordering для chunks.
18. Экспорт результатов в PDF.
19. Сравнение двух попыток self-check.
20. Notifications / push для supervisor.

---

## 6. Ограничения этого аудита

- Скриншоты «до» не сняты — нет визуальной фиксации текущего состояния. План: при наличии рабочего расширения снять отдельным проходом, либо положиться на саму защиту галереи «после».
- Не проверены mobile/tablet — не приоритет для defense-context.
- Пилотный тенант `optics-kafedra` пуст по пользователям → невозможно эмпирически проверить supervisor/student-флоу. Это превращается в зависимость для Фазы 6 (seed_demo).
