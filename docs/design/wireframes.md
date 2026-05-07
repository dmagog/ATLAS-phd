# Wireframes — структура P0/P1-экранов

> **Версия:** 0.1 (2026-05-07)
> **Метод:** structural drafts с использованием [`design-system v0.1`](design-system.md). Не «серые блоки», как изначально планировалось в роадмапе — поскольку дизайн-система уже готова, рисовать low-fi и потом переделывать было бы двойной работой. Полировка edge-cases / motion / тонкая копирайт-работа — Фаза 4.
> **Live:** все экраны доступны на работающей системе под префиксом `/_/wf/*`.
> **Контекст:** [`docs/design-roadmap.md`](../design-roadmap.md) Фаза 3.

---

## 1. Архитектура wireframes

### 1.1 Параллельность с production

Wireframes лежат в [`src/atlas/templates/wf/`](../../src/atlas/templates/wf/). Production-шаблоны ([`chat.html`](../../src/atlas/templates/chat.html), [`selfcheck.html`](../../src/atlas/templates/selfcheck.html), [`history.html`](../../src/atlas/templates/history.html), [`admin.html`](../../src/atlas/templates/admin.html), [`index.html`](../../src/atlas/templates/index.html), [`base.html`](../../src/atlas/templates/base.html)) **не тронуты**. Это позволяет:

- Свободно итерировать структуру без поломок prod;
- Прямое сравнение «до / после» одним переключением URL;
- Чистую миграцию в Фазе 5: просто переносим логику / API-вызовы из старых шаблонов в новые, потом удаляем старые;
- Удобный fallback при защите, если что-то отвалится в новой версии.

После завершения Фазы 5 каталог `wf/` удаляется одной командой, его роуты в `web.py` — тоже.

### 1.2 Общий layout

Каждый wireframe (кроме login) расширяет [`wf/_layout.html`](../../src/atlas/templates/wf/_layout.html), который даёт app-shell:

```
┌─────────────┬───────────────────────────────────┐
│ Sidebar     │ Topbar (tenant-ctx, user, theme)  │
│ (240px)     ├───────────────────────────────────┤
│             │                                   │
│ role-aware  │ Content                           │
│ navigation  │ (chat-mode 920px / dash 1280px)   │
│             │                                   │
└─────────────┴───────────────────────────────────┘
```

Sidebar генерируется через макросы из [`wf/_partials.html`](../../src/atlas/templates/wf/_partials.html): `sidebar_student`, `sidebar_supervisor`, `sidebar_tenant_admin`, `sidebar_super_admin`. Каждая роль имеет свою навигацию (см. реализацию).

Login — единственный экран без app-shell (двухколоночный layout brand-left + form-right).

---

## 2. Реестр экранов

| URL | Шаблон | Роль (контекст) | Приоритет | Что показывает |
|---|---|---|---|---|
| [`/_/wf/login`](http://127.0.0.1:8731/_/wf/login) | [wf/login.html](../../src/atlas/templates/wf/login.html) | анонимный | P0 | Brand-side с тезисами защиты + form-side (email/password + invite-code-flow) |
| [`/_/wf/chat`](http://127.0.0.1:8731/_/wf/chat) | [wf/chat.html](../../src/atlas/templates/wf/chat.html) | student | P0 | Чат + правая source-panel + inline citations + hard-gate badge + live typing-state |
| [`/_/wf/refusal`](http://127.0.0.1:8731/_/wf/refusal) | [wf/refusal.html](../../src/atlas/templates/wf/refusal.html) | student | P0 | First-class hard-gate screen с breach-метриками |
| [`/_/wf/eval`](http://127.0.0.1:8731/_/wf/eval) | [wf/eval.html](../../src/atlas/templates/wf/eval.html) | super-admin | P0 | 3 hero-cards + bar-cmp по 6 топикам + полная таблица + κ-rubric + воспроизводимость |
| [`/_/wf/selfcheck`](http://127.0.0.1:8731/_/wf/selfcheck) | [wf/selfcheck.html](../../src/atlas/templates/wf/selfcheck.html) | student | P0 | Hero score + rubric grid + per-question breakdown (MC + open) |
| [`/_/wf/supervisor`](http://127.0.0.1:8731/_/wf/supervisor) | [wf/supervisor.html](../../src/atlas/templates/wf/supervisor.html) | supervisor | P1 | 4 hero-cards + heatmap 12×6 + темы внимания + последняя активность |
| [`/_/wf/tenant-admin`](http://127.0.0.1:8731/_/wf/tenant-admin) | [wf/tenant-admin.html](../../src/atlas/templates/wf/tenant-admin.html) | tenant-admin | P1 | Программа с покрытием по топикам + инвайты + пользователи |

**Итого: 7 экранов + 2 базовых файла (layout + partials) = 9 шаблонов.**

История self-check (P2) и onboarding/invite-redeem (P2) сознательно не вошли в Фазу 3. Делаются в Фазе 5 при необходимости.

---

## 3. Каждый экран в деталях

### 3.1 Login ([wf/login.html](../../src/atlas/templates/wf/login.html))

**Назначение в demo-script:** шаг 0, первый кадр защиты.

**Структура:**
- **Левая колонка (brand-side):** логотип ATLAS-shield, тезис «Подготовка к кандидатскому минимуму с заземлением», 3 буллета с ключевыми результатами M3 (`refusal_tnr 1.000`, `κ 1.000`, кафедральный режим).
- **Правая колонка (form-side):** email/password, ссылка «забыли пароль» (placeholder), кнопка «Войти», divider, кнопка «Войти по инвайт-коду» с пояснением.

**Что демонстрирует комиссии:** продукт «упакован», брендирование живое, сразу заметно главное (защита от галлюцинаций), есть второй entrance-point (invite) → подразумевает мульти-тенант.

**Что доделать в Фазе 4–5:**
- Реальная отправка `POST /auth/login`, обработка ошибок.
- Реализация invite-redeem flow (отдельная страница или модалка).
- Адаптация под mobile (out-of-scope защиты, но базовый media-query уже есть).

### 3.2 Chat ([wf/chat.html](../../src/atlas/templates/wf/chat.html))

**Назначение в demo-script:** шаг 1, корректный вопрос → ответ с цитатами.

**Ключевые элементы:**
- Заголовок текущей темы + бейдж количества доступных материалов.
- Profile selector (Подробный / Краткий / Учебный) — оставлен из текущей реализации.
- 3 пузыря-сообщения: вопрос + ответ с inline `[1] [2] [3]` + второй вопрос с live typing-state (4 step-badges, текущий «Ищу в материалах»).
- Под ответом: badge `Hard-gate verified`, badge «3 источника · 4 чанка», latency, feedback thumbs.
- **Правая source-panel (360px):** 3 source-cards с index + title + page + snippet. Активна та, на которую кликнули в ответе.
- В нижней части source-panel — session-stats (сообщений / уникальных источников / hard-gate отказов).
- Composer внизу: textarea + большая кнопка «Отправить».

**Главный визуальный upgrade vs текущий chat.html:**
1. Source-panel — был tail-list, стал колонка с drill-down.
2. Inline numeric citations — было «(Born&Wolf, с.42)» в конце абзаца, стало `[1]` в строке.
3. Hard-gate badge — был невидим, стал явный.

**Что доделать:** реальные API-вызовы, реактивная подсветка active-source при клике на cite-pill, скролл-стейты длинного диалога.

### 3.3 Refusal ([wf/refusal.html](../../src/atlas/templates/wf/refusal.html))

**Назначение в demo-script:** шаг 2, **центральный аргумент диссертации**.

**Ключевые элементы:**
- Хлебные крошки «Вернуться к чату».
- Сверху — bubble с вопросом пользователя (контекст не теряется).
- Hero shield-icon (96×96), заголовок «Hard-gate: запрос отклонён», подзаголовок с акцентом «**до обращения к LLM**».
- 4 metric-cards: 2 «breach» (vector-score 0.31/0.55, чанков 0/2) с красной полоской слева + 2 нейтральных (latency 1.7s, LLM не вызван).
- Footnote: «refusal_tnr = 1.000 vs 0.000 у baseline».
- 2 CTA: «Задать другой вопрос» (primary) + «Посмотреть метрики» (ghost → ведёт на `/eval`).
- Под рефюзалом — карточка «темы, по которым корпус даёт ответы» с 6 топик-бейджами.

**Это не error-state, это first-class экран.** Демонстрация того, что отказ — продуманное поведение, а не ошибка.

**Что доделать:** реальные значения (vector-score, chunks, latency) подставляются из retrieval-trace API.

### 3.4 Eval ([wf/eval.html](../../src/atlas/templates/wf/eval.html))

**Назначение в demo-script:** шаг 3 + шаг 7, **главный носитель цифр диссертации**.

**Структура:**
- Заголовок + timestamp последнего прогона + кнопка «Перезапустить».
- **3 hero-cards в верхнем ряду:** `refusal_tnr 1.000` (с baseline 0.000 как зачёркнутая сравниваемая цифра), `κ 1.000`, `<2s` latency. Под каждой — короткое пояснение и BDD-ссылка.
- **Bar comparison по топикам:** 6 строк (Геом / Волн / Поляр / Дисп / Интерф / Дифр), каждая — пара полос baseline vs verifier с numeric-значениями справа.
- **Полная таблица** с per-topic breakdown: faithfulness, citation accuracy, refusal_tnr, latency p95, N. Нижний tfoot с агрегатом.
- Внизу — две карточки рядом: rubric agreement (4 cells κ по критериям) + воспроизводимость (4 metric-cards: 6/7 в σ<0.02, 7/7 одинаковые refusal-исходы, ±0.01 разброс κ, ±0.3s разброс latency).

**Это самая ресурсоёмкая страница** (17 KB HTML) — носит большую часть нарратива.

**Что доделать:** подключение к JSON-выводу [`eval/runner.py`](../../eval/runner.py), новый router `eval.py` (отсутствует), кнопка «Перезапустить» с фоновой job.

### 3.5 Selfcheck ([wf/selfcheck.html](../../src/atlas/templates/wf/selfcheck.html))

**Назначение в demo-script:** шаг 4, рубрика в действии.

**Структура (показано **состояние результата**, не процесс):**
- Hero: большой score `4.2/5` + verdict + summary + badge `κ 1.000 vs expert`.
- Rubric grid (4 cells: Точность 4.5 · 40%, Полнота 3.0 · 30%, Логика 4.5 · 20%, Терминология 3.5 · 10%) с цветной полоской слева.
- Evaluator summary в синей карточке-выноске.
- 6 per-question карточек с цветным фоном (зелёный/жёлтый/красный по статусу): MC с подсветкой правильного и зачёркиванием неверного, open-ended с показом ответа студента + замечанием эксперта.
- 2 CTA внизу: «К истории» / «Новая проверка».

**Главный upgrade vs текущий selfcheck.html:**
1. Hero — был плотный текст, стал hero-зона с большой цифрой.
2. Rubric — был такой же грид, но без указания весов; теперь явно `40% / 30% / 20% / 10%`.
3. κ-badge — добавлен (раньше отсутствовал в продукте).

**Состояния, которые НЕ показаны** (доделать в Фазе 4):
- Стартовый экран (ввод темы, шаги генерации) — повторяет паттерн чата, не критично для defense-демо.
- Состояние «в процессе прохождения» — было бы логично, но избыточно для 1 wireframe.

### 3.6 Supervisor ([wf/supervisor.html](../../src/atlas/templates/wf/supervisor.html))

**Назначение в demo-script:** шаг 5 (P1), кафедральный режим.

**Структура:**
- Заголовок + селект сортировки + экспорт.
- 4 hero-cards: студентов / активны за неделю (с delta `+2`) / средний score / топиков <60% покрытия.
- Heatmap-карточка: 12 студентов с avatar + ФИО × 6 топиков (Геом / Волн / Поляр / Дисп / Интерф / Дифр). Цветная заливка по последнему score, серая ячейка `—` для отсутствующих попыток.
- Шкала heatmap'а в шапке карточки.
- Снизу — 2 карточки рядом:
  - **«Темы, требующие внимания»**: 3 строки с warning-badge, описанием и кнопкой drill-down.
  - **«Последняя активность»**: 5 событий (студент + топик + score + when), без раскрытия текста ответов.

**Privacy:** в подзаголовке heatmap явно сказано «Текст ответов студента не показывается (M5 supervisor-privacy)». Это ключевой тезис M5 в визуальной форме.

**Что доделать:** drill-down модалка / отдельная страница попытки (с агрегатом, без текста); подключение к `/{slug}/supervisor/heatmap` API.

### 3.7 Tenant-admin ([wf/tenant-admin.html](../../src/atlas/templates/wf/tenant-admin.html))

**Назначение в demo-script:** шаг 6 (P1), платформенность.

**Структура:**
- Заголовок «Программа кафедры» + кнопки «Редактировать» / «Добавить топик».
- 4 hero-cards: топиков / материалов (3 учебника · 2,847 чанков) / среднее покрытие (87%) / активных пользователей (14, с разбивкой по ролям).
- **Левая колонка (2/3 ширины):** список 6 топиков, каждый — карточка с purpose-bar заполнения корпуса (зелёный ≥85% / жёлтый ≥60% / красный <60%), бейджами материалов, кнопкой drill-down.
- **Правая колонка (1/3):**
  - Карточка «Активные инвайты»: 3 строки с code, role-badge, uses · TTL, кнопкой copy.
  - Карточка «Недавние пользователи»: 5 строк с avatar + role-badge + ссылкой «Все пользователи →».

**Что демонстрирует:** «Новая кафедра = заполнить программу + загрузить материалы + раздать инвайты». Это и есть платформенность по принципу M4.A.

**Что доделать:** редактор топика как модалка / отдельная страница; страница «Все пользователи» с поиском и фильтрами; полноценный invite-create flow.

---

## 4. Технические наблюдения

### 4.1 Сильные стороны дизайн-системы

После сборки 7 экранов реальные находки:

1. **Hero-card** оказался самым переиспользуемым компонентом — стоит в `/eval`, supervisor, tenant-admin (всего 11 instances). Решение вынести в дизайн-систему оправдалось.
2. **Heatmap-cell** одинаково работает и в supervisor (12×6 grid), и как single-cell индикатор в «последней активности».
3. **Bar-cmp** прижился только в `/eval` — но там он критичен. Не over-engineering.
4. **Sidebar role-aware макросы** — DRY-выигрыш существенный: 4 макроса вместо 7 inline-навигаций.
5. **Tenant-ctx role-badge** оказался полезен и в topbar, и в users-table tenant-admin'а.

### 4.2 Недостатки, всплывшие в процессе

1. **`.field` отступы между лейблом/инпутом** — слишком плотные на login. Возможно, стоит ввести `.field--lg` или просто увеличить `--sp` для login-карточки локально.
2. **Состояние focused для `.input`** — синяя рамка хорошо видна на light, на dark теряется (хотя `box-shadow: 0 0 0 3px var(--c-primary-bg)` помогает). Проверить контраст в Фазе 4.
3. **Heatmap'у нужен hover-tooltip** с полной датой попытки и количеством попыток — сейчас только title-attribute.
4. **Refusal экран на узких viewport** ломается (overlay с 600px max-width в самом центре, при <600 нужен fallback). Out-of-scope защиты, но в TODO.
5. **`.bar-cmp__row` grid 140 / 1fr / 60** теряется на узких карточках. Возможно, нужен responsive-вариант через container queries (новые браузеры). Отложено.

### 4.3 Sample data

Вся sample data — **детерминированная**, hard-coded в Jinja2-set'ах. Это значит:
- Скриншоты воспроизводимы (одни и те же цифры между прогонами).
- Можно сделать «случайно красивые» цифры (например, на heatmap'е я расположил студентов так, что верхняя левая зона зелёная, нижняя — пёстрая — это «работает» визуально).
- В Фазе 5, когда подключаем реальные API, нужно держать эту структуру в `seed_demo.sh`, чтобы скриншоты остались похожими.

---

## 5. Чек-лист перехода к Фазе 4

- [x] 7 P0/P1 экранов имеют структурный draft.
- [x] Все используют design-system v0.1 без inline-стилей (за исключением мелких ad-hoc).
- [x] Theme-toggle работает на всех экранах.
- [x] Sidebar role-aware (4 роли × соответствующие пункты).
- [x] Все ссылки между wireframes (refusal → chat / eval; tenant-admin → users; etc.) ведут на верные `/_/wf/*` URL.
- [x] Все 7 роутов отвечают 200 OK.
- [ ] Нет проверки контраста (Фаза 4).
- [ ] Нет проверки keyboard-nav (Фаза 4).
- [ ] Нет live-data (Фаза 5).
- [ ] Demo-data в `seed_demo.sh` ещё не приведён в соответствие с wireframe-data (Фаза 6).

---

## 6. Changelog

- **0.1 (2026-05-07):** 7 wireframes (login / chat / refusal / eval / selfcheck / supervisor / tenant-admin) + общий layout + макросы навигации. Все на дизайн-системе v0.1, рендерятся, общий объём ~95 KB HTML. Решение делать structural drafts вместо grey-box wireframes зафиксировано.
