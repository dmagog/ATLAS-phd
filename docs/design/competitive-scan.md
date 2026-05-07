# Competitive Scan — паттерны для demo-grade UI

> **Версия:** 0.1 (2026-05-07)
> **Метод:** анализ того, что **выглядит круто на демо** (а не «удобно в эксплуатации»). Источник — публичные landing-страницы, доки, публичные демо, скриншоты product-tour'ов. Без логина под пейволлами.
> **Контекст:** [`docs/design-roadmap.md`](../design-roadmap.md) Фаза 1.

---

## 1. Кто и почему попал в выборку

Четыре референса покрывают разные грани нашего продукта:

| Референс | Грань ATLAS, на которую ложится | Что заимствуем |
|---|---|---|
| **NotebookLM** (Google) | RAG над пользовательским корпусом | Source-panel, citation UX, hero-страница с «о чём этот корпус» |
| **Perplexity** (Spaces) | Q&A с inline-цитатами, типизация ответа по профилю | Citation-chips, follow-up suggestions, focus-режим |
| **Linear** | Multi-tenant + role-aware navigation, dashboard density | Sidebar, status pills, табличные виды, командные палитры |
| **Vercel Dashboard / Analytics** | Презентация чисел и метрик | Hero-cards с большими цифрами, sparkline, comparison-bars |

Намеренно **не берём** Anki / RemNote / ChatGPT Edu — они либо устарели визуально (Anki), либо closed (Edu), либо общий чат без RAG-специфики (ChatGPT).

---

## 2. Паттерны под наши P0-экраны

### 2.1 Q&A с цитатами → NotebookLM + Perplexity

**Что у них работает:**
- **Numbered citation pills** прямо в строке ответа: «...закон Ферма [1]...», где `[1]` — кликабельная пилюля.
- **Source-panel справа**: при клике на `[1]` подсвечивается соответствующий чанк в правой колонке с именем документа, страницей и snippet'ом.
- **Citation hover**: tooltip с превью чанка, без перехода.
- **«Verified» indicator** (Perplexity Pro): значок щита рядом с ответом, подразумевающий «проверено».

**Что забираем для ATLAS:**
- Inline numeric citations `[1] [2]` вместо нашего «(Born&Wolf, с.42)» в конце абзаца. У нас уже есть `data.citations`, нужно перейти от tail-list к inline-pill.
- Source-panel справа от чата (вторая колонка `1fr 380px`): открывается на клик по pill. Внутри — title + страница + snippet чанка + ссылка «открыть документ» (M6).
- **Hard-gate badge** «Verified by retrieval gate» с tooltip — это наш аналог «Verified», но **прямо на каждый ответ**, а не как pro-feature.

**Чего избегаем:** Perplexity «follow-up» загромождает чат тремя suggested-questions после каждого ответа. Для defense-демо это distract. Можно добавить как опцию.

---

### 2.2 Refusal-экран → NotebookLM «no source coverage»

**Что у NotebookLM:**
- Когда вопрос не покрыт корпусом, NotebookLM возвращает: «I couldn't find that in your sources» + предложение «попробуйте задать вопрос по [X], [Y]».
- Это обычное сообщение, не выделено как «защитный механизм».

**Что мы делаем иначе:**
- У нас refusal — **аргумент диссертации** (`refusal_tnr 1.000 vs 0.000`). Поэтому делаем его **first-class экраном**, а не сообщением в чате. Hero-зона с иконкой shield, заголовок «Hard-gate активирован», под ним: какие пороги были превышены (`top1_vscore < 0.55` или `chunks_above_threshold < 2`), сколько фрагментов нашлось, почему это правильное поведение.

Это паттерн, **которого ни у кого нет** — именно поэтому он сработает на защите.

---

### 2.3 Self-check рубрика → нет прямого аналога; берём из Linear/Vercel

Образовательных продуктов с визуализацией рубрики типа «correctness 40 / completeness 30 / logic 20 / terminology 10» в публичном поле почти нет. Самые близкие референсы:

- **Linear «Triage»**: 4 priority-pills с разной заливкой; читаются за полсекунды.
- **Vercel «Lighthouse score»**: 4 кольцевых индикатора (Performance / Accessibility / Best Practices / SEO), каждый — большой numeric + цвет.

**Что забираем:**
- Hero-зона: один большой score (`4.2 / 5`) + verdict + sparkline из последних попыток по этой теме.
- Под ней: 4 равных hero-cell с критериями (`Точность 4.5 / 5  • вес 40%`), каждая ячейка цветная по score-color.
- В отличие от Vercel колец — у нас прямоугольные ячейки (проще для скриншота).

---

### 2.4 Supervisor dashboard → Linear Issues + Vercel Analytics

**API уже даёт `heatmap` и `students` list.** На UI это собирается в:

- **Sidebar**: «Студенты» (число), «Программа» (топиков), «Материалы» (чанков), «Аудит». Стиль — Linear-like.
- **Главный экран — heatmap**: студенты строки × топики колонки, ячейки цветные по последнему score (или «нет попыток» — серая). При клике на ячейку — drill-down на конкретную попытку.
- **Hero-cards над heatmap'ом**: «Студентов: 24», «Активных за неделю: 18», «Средний score: 3.6», «Тем с покрытием < 60%: 4». Стиль — Vercel Analytics: большая цифра + малый delta (`+2 vs прошлая неделя`).

---

### 2.5 Eval-дашборд → Vercel Analytics + Vercel Speed Insights

**У нас будет** уникальная страница «Eval results», которой нет ни у кого из референсов в публичном виде:

- **Hero-row** (3 cards):
  1. `refusal_tnr` — большая цифра `1.000` + сравнение `vs baseline 0.000` + bar.
  2. `κ_binarized` — `1.000` + подпись «agreement with expert».
  3. `p95 latency` для hard-gate refusal — `<2s` + бар.
- **Bar comparison**: per-topic faithfulness (baseline / verifier) — горизонтальные пары полос, как в Vercel Speed Insights «before/after deploy».
- **Heatmap**: топик × метрика, заливка по score.

Это и есть **главный носитель нарратива диссертации**. Без него вся защита держится на устных утверждениях.

---

### 2.6 Navigation → Linear sidebar

- **Sidebar** (collapsible) вместо topbar — даёт больше места для role-aware пунктов и текущего tenant.
- В верху sidebar: **tenant switcher** (для super-admin) + role badge.
- Иконки + labels (для проектора labels должны быть видны всегда, не на hover).
- Active state — слева цветная полоска + выделенный фон, как в Linear.

Это требует переход с `<header><nav>` на двухколоночный layout. **Один из крупных визуальных upgrade'ов** Фазы 4.

---

## 3. Дизайн-токены, которые забираем

| Токен | Откуда | Значение |
|---|---|---|
| Sidebar background (dark) | Linear | `#1c1c1f` |
| Card / surface (dark) | Linear | `#252528` |
| Text primary (dark) | Linear | `#e6e6e6` |
| Accent / brand (dark) | наш `calm-blue` из `branding/` | `#5b88c2` (примерно, точный — из SVG) |
| Hero numeric font-weight | Vercel | `700` |
| Hero numeric font-size | Vercel | `2.5rem–3rem` |
| Status pill height | Linear | `20–24px` |
| Border radius | Vercel | `8px` cards, `6px` buttons, `100px` pills |
| Animation | Linear | 150–200ms ease-out |

---

## 4. Паттерны, **которых избегаем**

| Антипаттерн | Откуда | Почему не нам |
|---|---|---|
| Multi-step wizard для основных действий | многие SaaS | Задерживает demo-flow |
| Onboarding tour overlays | Notion / Vercel | Перекрывают скриншот |
| «AI sparkle» иконки на каждой кнопке | новые AI-продукты 2025 | Девальвирует значение наших AI-моментов |
| Skeleton loaders длиннее 1.5 сек | многие SPA | На демо ждать неловко |
| Pricing-style hero cards с большими `$` | SaaS landing'и | Мы не SaaS |

---

## 5. Что взять в Фазу 2 (дизайн-система)

Список компонентов, которые точно нужны (синтез разделов выше):

1. `Sidebar` (Linear) с tenant-switcher, role-badge, navigation.
2. `HeroCard` (Vercel) — большая цифра + подпись + сравнение/sparkline.
3. `CitationPill` (Perplexity) — inline numeric, кликабельная.
4. `SourcePanel` (NotebookLM) — правая колонка, чанки.
5. `RefusalScreen` (наш паттерн) — first-class hero с shield-иконкой и метриками.
6. `RubricGrid` (наш + Vercel Lighthouse) — 4 ячейки с весами.
7. `Heatmap` (Linear «Cycle view») — студент × топик.
8. `BarComparison` (Vercel Speed Insights) — baseline / verifier пары.
9. `StatusPill` (Linear) — единый компонент для tenant status / attempt status / ingestion status.
10. `EmptyState` (NotebookLM) — отдельный компонент с иконкой + CTA, не просто `<p>`.
