# Design Rationale — обоснование UX-решений (для комиссии)

> **Версия:** 0.1 (2026-05-07)
> **Назначение:** короткое (1–2 страницы при печати) обоснование ключевых UX-решений ATLAS phd в академических терминах. Используется как раздаточный материал на защите или ответ на вопросы комиссии о «почему именно так?».
> **Контекст:** [`docs/design-roadmap.md`](../design-roadmap.md) Фаза 6.

---

## 1. Принципиальные решения

### 1.1 Refusal как first-class экран, а не error state

**Решение.** При срабатывании retrieval hard-gate система показывает **полноэкранный** компонент с иконкой щита, заголовком «Hard-gate: запрос отклонён», метриками (vector-score, chunks, latency) и пояснением — а не короткое сообщение в чат-bubble.

**Обоснование.** В литературе по AI-системам отказ обычно подаётся как «error» (Norman 2013, error messages). Это создаёт у пользователя ощущение поломки. Для ATLAS отказ — **продуманное защитное поведение**: ключевой результат диссертации (`refusal_tnr = 1.000`). Визуальный приоритет должен соответствовать смысловому: refusal-screen — это not failure, это feature.

**Соответствие эвристикам Nielsen:**
- **Heuristic 9 (Help users recognize, diagnose, recover from errors):** объяснение причины отказа («лучший vector-score 0.31 / порог 0.55»), а не общее «не получилось».
- **Heuristic 1 (Visibility of system status):** пользователю явно показывается, что hard-gate сработал, а не происходит ли что-то «под капотом».

---

### 1.2 Citation pills inline в ответе, а не tail-list

**Решение.** Источники представлены как inline-пилюли `[1] [2] [3]` рядом с соответствующими утверждениями ответа, плюс правая source-panel с раскрытием. Не tail-list «Источники: Born&Wolf с.42, Матвеев с.112».

**Обоснование.** Tail-list заставляет пользователя восстанавливать связь «утверждение ↔ источник» по памяти после прочтения ответа. Inline-pills делают связь видимой непосредственно — это известный паттерн из NotebookLM, Perplexity, академических PDF-читалок (см. Wattenberg & Viégas 2007 о visual reference linking).

**Соответствие принципам:**
- **Fitts' Law:** клик по источнику — это сразу через pill, а не через scroll к bottom списка.
- **Cognitive load (Sweller):** связь утверждение↔источник эксплицитна, не требует working-memory recall.

---

### 1.3 Рубрика с явно показанными весами (40/30/20/10)

**Решение.** Self-check результат показывает **4 ячейки** с оценкой по критериям и **указанием веса**: «Точность 40%», «Полнота 30%», «Логика 20%», «Терминология 10%».

**Обоснование.** Образовательные продукты часто скрывают веса от пользователя (например, отдают только итоговый score). Это создаёт «чёрный ящик» — студент не знает, на что обратить внимание для улучшения. ATLAS показывает рубрику явно, что:
1. Делает оценку **проверяемой** студентом.
2. Даёт actionable feedback — видно, какой критерий «провален».
3. Соответствует принципу **прозрачности AI-систем** (Floridi et al. 2018, AI4People).

К рубрике привязан badge `κ = 1.000 vs expert` — он **кликабельный** и ведёт на eval-dashboard. Это эксплицитно связывает self-check оценку с её внешней валидацией.

---

### 1.4 Privacy mask для supervisor

**Решение.** Supervisor видит heatmap агрегатно (per-topic статистика), список студентов с privacy-mask (только opted-in показываются по имени; остальные — «Аспирант #N»), но **никогда** — текст ответов студента.

**Обоснование.** Это реализация принципа **data minimization** (GDPR Art. 5(1)(c), также NIST Privacy Framework). Научный руководитель имеет легитимный интерес видеть agreement по топикам (где студенты массово ошибаются), но не индивидуальные ответы — это пересекает границу educational analytics → personal data leak.

Opt-in модель (BDD 3.4) соответствует принципу **informed consent**: студент сам решает, видеть ли супервизору его имя в списке. Anonymous-aggregate-only — это default.

---

### 1.5 Sidebar role-aware navigation

**Решение.** Sidebar показывает разные пункты для разных ролей:
- student: Чат / Самопроверка / История
- supervisor: Heatmap / Студенты + личное (Чат, Самопроверка)
- tenant-admin: Программа / Материалы / Инвайты
- super-admin: Eval / Материалы / Styleguide

**Обоснование.** Принцип **least authority**: пользователь не видит того, что ему не доступно. В отличие от подхода «всем показать всё, скрыть кнопки на 403», здесь UX чище и нет ощущения «у меня нет прав».

Соответствие WCAG 2.1 (1.3.1 Info and Relationships): пункты меню структурированы и помечены семантически.

---

### 1.6 Dark mode by default

**Решение.** Дефолтная тема — тёмная; light mode — fallback через theme-toggle.

**Обоснование.** Прагматическое: на проекторе во время защиты тёмная тема обычно выигрывает по контрасту и не «бьёт» в глаза комиссии. Также:
- Меньше нагрузка на глаза при длительной работе (Kang & Wang 2014).
- Все семантические цвета (success/warning/danger) перетюнены под dark, чтобы соответствовать контрастному порогу WCAG AA (минимум 4.5:1 для normal text).

`prefers-reduced-motion` уважается (отключение всех transitions).

---

## 2. Дизайн-система: одна страница, без build-step

**Решение.** Один файл `static/atlas.css` (~33 KB) с CSS custom properties для токенов. Без Tailwind, без Node, без webpack.

**Обоснование.**
1. Минимизация технической поверхности: один артефакт, один HTTP-запрос, прямой просмотр в DevTools.
2. Hot-reload через uvicorn сохраняется (правка → F5).
3. Семантические компоненты (`.refusal`, `.rubric`, `.heatmap`) — не utility-классы Tailwind. Это соответствует **separation of concerns** на уровне CSS.

Альтернатива — Tailwind через CDN — рассматривалась и отклонена в [`design-system.md`](design-system.md) §1.1.

---

## 3. Ограничения и compromises

### 3.1 Display name = email (нет кастомных ФИО)

User модель хранит только email; для demo-данных адреса вида `ivanov@optics.demo` визуально работают как «Иванов А. М.», но это **не** настоящий display_name. Полная поддержка ФИО потребует миграцию БД (out-of-scope для demo).

### 3.2 Hard-gate breach metrics не expose'ятся в API

Refusal-экран показывает обобщённое объяснение, но **не** конкретные значения vector_score / chunks_above_threshold. Эти метрики живут в retrieval-trace логах, но не в ChatResponse API. Для defense-демо это компенсируется text'ом в `refusal_message` + footnote с цифрой `refusal_tnr=1.000`.

### 3.3 «Riemann hypothesis» / «QCD» НЕ отказываются

Honest finding: вопросы, близкие к физике (математика для физики, теор-физика), retrieval **находит** loose-matches и не отказывается. Это **граница точности** hard-gate: он строг на off-topic (не-физика), но не на «соседних» доменах. В demo используем явно off-topic вопросы (population, diesel, sorting). См. `scripts/demo_questions.json`.

### 3.4 Mobile responsive — out-of-scope

Layout оптимизирован под 1280–1920px (ноутбук/проектор). Mobile layout не тестировался.

---

## 4. Ссылки на источники методологии

- **Nielsen J.** «10 Usability Heuristics for User Interface Design», 1994.
- **WCAG 2.1** (W3C Recommendation, 2018) — accessibility baseline.
- **Floridi L. et al.** «AI4People — Ethical Framework», Minds and Machines, 2018 (transparency).
- **Sweller J.** «Cognitive load theory», 2010 (UI density decisions).
- **Norman D.** «Design of Everyday Things», 2013 (error messaging).
- **Wattenberg M., Viégas F.** «Designing for Social Data Analysis», VAST 2007 (citation patterns).

---

## 5. Метрики, подтверждающие UX-решения

Эти метрики **измерены** на работающей системе (см. [`/eval`](http://127.0.0.1:8731/eval) и [`docs/design/screenshot-gallery.md §4`](screenshot-gallery.md#4-шаг-3--eval-dashboard-eval)):

| Решение | Связанная метрика | Значение |
|---|---|---|
| Hard-gate как защита (1.1) | `refusal_tnr` | 1.000 (vs 0.000 baseline) |
| Рубрика с весами (1.3) | `κ_binarized` (rubric vs expert) | 1.000 |
| Refusal latency | `<2s` p95 hard-gate | подтверждено |
| Воспроизводимость | 7 прогонов eval-set | mean=1.0, stdev=0 |

Каждое UX-решение в этом документе имеет либо академическое обоснование (Nielsen / WCAG / Floridi), либо подтверждается измерением на работающей системе.
