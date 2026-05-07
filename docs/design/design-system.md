# Design System v0.1 — токены и компоненты

> **Версия:** 0.1 (2026-05-07)
> **Артефакты:** [`src/atlas/static/atlas.css`](../../src/atlas/static/atlas.css), [`src/atlas/templates/_styleguide.html`](../../src/atlas/templates/_styleguide.html), [`src/atlas/static/icons/`](../../src/atlas/static/icons/)
> **Live:** [`/_/styleguide`](http://127.0.0.1:8731/_/styleguide) (после `docker compose up -d`)
> **Контекст:** [`docs/design-roadmap.md`](../design-roadmap.md) Фаза 2.

---

## 1. Технические выборы

### 1.1 CSS-стек: чистый CSS + переменные, без Tailwind

В роадмапе допускались Tailwind-CDN или standalone-CLI. После аудита (см. [`ux-audit.md`](ux-audit.md)) и competitive-scan выбрана **бесbuild'овая опция**: один файл [`atlas.css`](../../src/atlas/static/atlas.css) (~600 строк) с CSS-переменными для токенов и BEM-ish классами компонентов.

**Почему так:**
- Дизайн-язык **специфичен** (sidebar Linear-style, source-panel NotebookLM, hero-cards Vercel, refusal-screen — наш). Tailwind utility-классы для этого избыточны и зашумляют разметку.
- Нет Node/npm в стеке. Tailwind standalone CLI работает, но требует отдельный binary, скрипт, артефакт сборки. Лишняя движущаяся часть.
- Hot-reload через uvicorn `--reload` уже работает: edit → save → F5. Build-step разрушит этот цикл.
- При необходимости Tailwind можно добавить позже инкрементально (`@apply` в CSS-уровне), не меняя архитектуру.

**Стоимость решения:** при росте проекта или появлении дизайнера (после защиты) может потребоваться миграция на Tailwind. Это терпимо: токены уже в CSS-переменных, маппинг 1:1.

### 1.2 Темизация

`[data-theme="dark"]` на `<html>`. По умолчанию — **dark** (см. принцип №4 в `design-roadmap.md`). Light-режим — fallback. Все токены продублированы в обеих палитрах.

### 1.3 Иконки

Bootstrap Icons через CDN (как было) — не меняем, ради скорости итерации. Бренд-иконка из [`docs/branding/variants/atlas-icon-v5-shield-no-ring-calm-blue.svg`](../branding/variants/atlas-icon-v5-shield-no-ring-calm-blue.svg) скопирована в [`src/atlas/static/icons/atlas-shield.svg`](../../src/atlas/static/icons/atlas-shield.svg) и используется в sidebar / refusal / favicon.

### 1.4 Layout-режимы

- `app__content--chat` — `max-width: 920px` (Q&A, history, обычные пользовательские флоу).
- `app__content--dashboard` — `max-width: 1280px` (eval, supervisor, tenant-admin).

Sidebar — `240px`, фиксированной ширины. Source-panel — `360px`, в собственном контейнере.

---

## 2. Токены (полный реестр)

### 2.1 Цвет

Токены light/dark парные. Полный список — в `:root` и `[data-theme="dark"]` секциях [`atlas.css`](../../src/atlas/static/atlas.css).

| Группа | Токены | Назначение |
|---|---|---|
| Бренд | `--brand-blue` `--brand-slate` | Извлечены из SVG `atlas-icon-v5-shield-no-ring-calm-blue`. Используются точечно (логотип, акценты в hero) |
| Поверхности | `--c-bg` `--c-surface` `--c-surface-2` | Фон страницы / карточки / вторичный контейнер |
| Границы | `--c-border` `--c-border-strong` | Тонкая / выраженная |
| Текст | `--c-text` `--c-text-2` `--c-text-3` | Основной / приглушённый / вспомогательный |
| Семантика | `--c-primary` `--c-success` `--c-warning` `--c-danger` + `*-bg` варианты | Каждой роли — пара (заливка-фон) |
| Heatmap | `--c-heat-0..5` | Шкала для supervisor heatmap, согласована с success/warning/danger |

### 2.2 Типографика

| Токен | px | Использование |
|---|---|---|
| `--fs-xs` | 12 | Подписи, метаданные, dot-badges |
| `--fs-sm` | 13 | Таблицы, компактные списки, меню |
| `--fs-base` | 15 | Базовый текст интерфейса (повышен с 14 для проектора) |
| `--fs-md` | 16 | Заголовки секций |
| `--fs-lg` | 18 | Section heading на дашбордах |
| `--fs-xl` | 22 | Page title |
| `--fs-2xl` | 30 | Major heading |
| `--fs-hero` | 44 | Цифры на eval-дашборде, score в self-check |

Шрифты: `system-ui` стек для UI, `ui-monospace` для цифр и кода.

### 2.3 Spacing

4px-base шкала: `--sp-1` (4) → `--sp-2` (8) → `--sp-3` (12) → `--sp-4` (16) → `--sp-5` (20) → `--sp-6` (24) → `--sp-8` (32) → `--sp-10` (40) → `--sp-12` (48).

### 2.4 Радиусы

- `--r-sm` (4) — мелкие элементы (badge dot, citation pill).
- `--r-md` (6) — кнопки, инпуты.
- `--r-lg` (8) — карточки, модалки-малые.
- `--r-xl` (12) — hero-карточки, refusal.
- `--r-pill` (999) — pill-badges.

### 2.5 Тени и motion

| Токен | Назначение |
|---|---|
| `--sh-sm` | Карточки в обычном состоянии |
| `--sh-md` | Hover, elevated cards, modals |
| `--sh-lg` | Toast, refusal, popovers |
| `--t-fast` (120ms) | Hover, focus |
| `--t-base` (180ms) | Большинство переходов |
| `--t-slow` (280ms) | Прогресс-бары, анимации появления |

---

## 3. Компоненты — реестр

| # | Класс | Где используется (предполагается) | Статус |
|---|---|---|---|
| 1 | `.btn` (`--primary` / `--secondary` / `--ghost` / `--danger`, `--sm` / `--lg` / `--icon` / `--block`) | Все экраны | ✅ готов |
| 2 | `.input` `.textarea` `.select` `.label` `.field` | Login, settings, admin | ✅ готов |
| 3 | `.card` (`--flat` / `--elevated` / `--interactive`) | Все экраны | ✅ готов |
| 4 | `.badge` (`--info` / `--success` / `--warning` / `--danger` / `--brand`) | Статусы, метки | ✅ готов |
| 5 | `.cite` | Inline-цитаты в Q&A | ✅ готов |
| 6 | `.hero-card` | `/eval` дашборд, supervisor metrics | ✅ готов |
| 7 | `.bar-cmp` | `/eval` baseline-vs-verifier | ✅ готов |
| 8 | `.rubric` | Self-check 40/30/20/10 | ✅ готов |
| 9 | `.refusal` | First-class hard-gate screen | ✅ готов |
| 10 | `.sidebar` `.app__topbar` `.tenant-ctx` | Глобальный layout | ✅ готов |
| 11 | `.source-panel` `.source-card` | Q&A правая колонка | ✅ готов |
| 12 | `.heatmap` `.heatmap__cell` | Supervisor dashboard | ✅ готов |
| 13 | `.spinner` `.step-badge` | Pipeline progress, loading | ✅ готов |
| 14 | `.overlay` `.modal` | Confirmations | ✅ готов |
| 15 | `.toast` | Краткие подтверждения | ✅ готов |
| 16 | `.bubble` (`--user` / `--atlas`) | Q&A чат | ✅ готов |
| 17 | `.empty` | Пустые списки | ✅ готов |
| 18 | `.tenant-ctx__role--*` | Role-бейджи в topbar | ✅ готов |

**Итого:** 18 компонентов. Цель из роадмапа была «12–15» — превышено по двум причинам: refusal-screen + bar-cmp + source-panel оказались отдельными первоклассными компонентами, которых в плане не было (всплыли в аудите).

---

## 4. Утилиты

В конце [`atlas.css`](../../src/atlas/static/atlas.css) — небольшой утилитарный слой (~30 классов):

- `.flex` `.flex-col` `.inline-flex` `.items-center` `.items-start` `.items-end` `.justify-between` `.justify-center` `.justify-end` `.flex-1` `.flex-wrap`
- `.gap-1..6` (с шагами spacing-токенов)
- `.grid` `.grid-cols-2` `.grid-cols-3` `.grid-cols-4`
- `.mt-1..6` `.mb-1..6` `.p-3..6`
- `.text-center` `.text-right`
- `.hidden` `.sr-only`

**Принцип:** утилиты покрывают то, что встречается часто и не имеет смысла оборачивать в компонент. При этом не дублируется логика Tailwind — мы не пытаемся быть Tailwind, мы покрываем 90% реальных случаев.

---

## 5. Accessibility-baseline

- Все интерактивные элементы имеют `:focus-visible` со стилем `outline: 2px solid var(--c-primary); outline-offset: 2px`.
- Контраст (тёмная тема): `--c-text` на `--c-bg` ≥ 13:1; `--c-text-2` на `--c-bg` ≥ 6.5:1; `--c-primary` на `--c-bg` ≥ 5.5:1 — все в зоне AA для normal text, большинство — AAA.
- `.sr-only` — для скрытых меток у иконочных кнопок.
- Семантическая иерархия заголовков соблюдается в styleguide; для реальных страниц — добавляется в Фазе 5.

**Что ещё нужно (Фаза 5):** aria-labels у иконочных кнопок, aria-live для toast'ов, focus-trap в модалках, skip-links.

---

## 6. Live styleguide

Доступен по `/_/styleguide` (без авторизации, но префикс `_/` сигнализирует внутреннее назначение). Включает:

1. Полную палитру с токенами
2. Heatmap-шкалу
3. Типографическую шкалу
4. Все варианты кнопок
5. Все формы (включая ошибочное состояние)
6. Карточки, бейджи, role-бейджи
7. Чат-пузыри с inline-цитатами и hard-gate badge
8. 3 hero-cards с цифрами защиты (`refusal_tnr 1.000`, `κ 1.000`, `<2s`)
9. Bar comparison по 6 топикам M4.5.E
10. Рубрику с реалистичным распределением
11. Refusal-экран с метриками breach
12. Heatmap 8 студентов × 6 топиков
13. Source-panel с 3 источниками (Born&Wolf / Матвеев / Yariv)
14. Empty-state, spinner, step-badges, toast, modal

**Toggle темы** в правом верхнем углу — позволяет визуально сверить контраст в обеих темах.

---

## 7. Что **не** в этой версии

- Нет компонента `.tabs` — добавится по необходимости в Фазе 5 (вероятно, нужен для tenant-admin: программа/материалы/инвайты).
- Нет компонента `.breadcrumb` — добавится при необходимости в supervisor drill-down.
- Нет компонента `.dropdown / select-custom` — нативный `<select>` пока хватает.
- Нет `.table-styled` — таблицы делаются ad-hoc через утилиты + custom CSS на месте. Вернёмся, если повторится 3+ раза.
- Нет `.form-validation` рамки — есть `field__error`, но нет реактивной валидации в стиле подсветки.
- Нет анимации появления карточек / страниц.

Все эти пробелы — **сознательные** для Фазы 2; добавим в Фазе 4–5, если конкретный экран потребует.

---

## 8. Как пользоваться при разработке экрана

1. Открыть `/_/styleguide` рядом с экраном — на нём видно все компоненты в живом виде.
2. Найти подходящий блок → скопировать разметку.
3. Если нужны утилиты — `flex`, `gap-N`, `grid-cols-N`, `mt/mb/p-N` уже есть.
4. **Не вводить новые цвета / spacing'и в inline-стилях.** Если нет нужного токена — добавить в `:root` (и в `[data-theme="dark"]`), потом использовать.
5. **Не дублировать стили из styleguide.** Если что-то повторяется в 2+ шаблонах — выносим в [`atlas.css`](../../src/atlas/static/atlas.css) как новый компонент.

---

## 9. Changelog

- **0.2 (2026-05-07, Фаза 4 полировка):** Добавлен дискретный «Phase 4 polish» блок (~6 KB) в конце [`atlas.css`](../../src/atlas/static/atlas.css). Изменения:
  - **Motion (раздел 26).** Keyframes `atlas-fade-in-up`, `atlas-scale-in`, `atlas-pulse-ring`. Stagger entrance для hero-card на дашбордах (60ms/120ms/180ms задержки). Refusal с `atlas-scale-in` (360ms) — emotional moment. Citation pill: `translateY(-1px)` на hover. Hard-gate badge: 2-кратный pulse-ring через 1.2s после загрузки (привлекает взгляд комиссии на demo). Полное уважение к `prefers-reduced-motion`.
  - **Focus (раздел 27).** Усилен `:focus-visible` на dark: outline `#93C5FD` + 4px box-shadow rgba(96,165,250,.2). На light оставлен primary outline.
  - **Bar-cmp responsive (раздел 28).** Container query (max-width: 480px) переключает grid на vertical (label/value сверху, pair снизу). Fallback через media (max-width: 720px) для старых браузеров.
  - **Field--lg (раздел 29).** Увеличенные отступы для login-формы.
  - **Heatmap tooltip (раздел 30).** CSS-only tooltip через `data-tip` атрибут. Появляется на hover с opacity-transition. Используется в supervisor heatmap с полным контекстом (ФИО · топик · score).
  - **Refusal narrow viewport (раздел 31).** При <600px — single-column metrics grid, уменьшенный icon (96 → 64), уменьшенный title.
  - **Card hover lift (раздел 32).** Subtle `translateY(-1px)` для interactive-cards.
  - **Source-card (раздел 33).** Hover: `translateX(2px)`. Active: fade-in entrance.
  - **Light-mode shadows (раздел 34).** Перетюнены через slate-tinted rgba (15, 23, 42) вместо нейтрального чёрного — выглядит «холоднее», подходит к brand-slate.
  - **Sidebar link (раздел 35).** Padding-left на hover увеличивается на 2px — мягкая обратная связь.
  - **Topbar sticky (раздел 36).** `position: sticky` для удержания контекста при скролле дашборда.
  - **Print (раздел 37).** Скрытие sidebar/topbar при печати — для возможного экспорта скриншотов через браузерное «Сохранить как PDF».

  Wireframes: aria-labels на всех icon-only кнопках (chat / eval / tenant-admin / supervisor), `<time>` элемент для timestamps, форма login с `for`/`id`-связками лейблов, role/gridcell aria для heatmap. κ-бейдж в selfcheck стал кликабельной ссылкой на `/eval`. Supervisor heatmap получил полные tooltip'ы с ФИО + топиком + score (исправлен Jinja-баг с shadowing внешнего `loop` во внутреннем).

  Closed: 5 находок из конца Фазы 3 (login density, focus-state на dark, heatmap tooltip, refusal narrow viewport, bar-cmp responsive). Verified: все 7 wf-роутов + styleguide отвечают 200, atlas.css 33.7 KB.

- **0.1 (2026-05-07):** Первая фиксация. 18 компонентов, light/dark темы, бренд-иконка интегрирована, styleguide рендерится через Jinja2 на `/_/styleguide`, рендер verified (200 OK, 44 KB HTML, 27 KB CSS).
