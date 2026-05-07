# Demo Recording Protocol — fallback-видео для защиты

> **Версия:** 0.1 (2026-05-07)
> **Назначение:** инструкция, как снять короткие screencast'ы 10–20 секунд для каждого LLM-зависимого момента демо. Эти записи — **страховка**: если в день защиты OpenRouter будет лагать или вернёт 5xx, можно показать видеозапись вместо живого прогона.
> **Артефакты:** записи сохраняются в `docs/design/screencasts/`. JSON-фикстуры реальных ответов лежат в `scripts/fixtures/` для справки.

---

## 1. Что снимать (3 ролика)

| # | Ролик | Длительность | Что показывает |
|---|---|---|---|
| 1 | `01-qa-with-citations.gif` | 15–25 с | Ввод вопроса → typing-state со step-badges → ответ с inline citation pills + source-panel |
| 2 | `02-refusal-screen.gif` | 5–10 с | Ввод off-topic вопроса → быстрое срабатывание hard-gate → first-class refusal-screen с метриками |
| 3 | `03-selfcheck-rubric.gif` | 30–45 с | Запуск self-check → генерация → ответы на 5 вопросов → результат с hero-score + rubric grid |

---

## 2. Подготовка

### 2.1 Состояние стенда

```bash
./scripts/seed_demo.sh
docker compose exec -T app python3 /app/scripts/verify_demo_questions.py --quick
```

Должно быть `2/2 PASS`. Если нет — не записывать, разбираться.

### 2.2 Браузер

* Chrome / Safari в **dark mode** (тема toggle в шапке должна показывать `Dark`).
* Окно ровно на **1440 × 900** (или close to it). На macOS можно использовать [Rectangle](https://rectangleapp.com/) или Window menu → Move & Resize.
* DevTools закрыт. Скрытые расширения отключены (особенно adblockers и автозаполнение пароля).
* Login как **`ivanov@optics.demo` / `demo`** (student-роль).

### 2.3 Инструмент записи

**Вариант A — macOS встроенное (рекомендуется):**
1. `Cmd + Shift + 5`
2. Кнопка «Записать выбранную область» → выделить только окно браузера.
3. После клика «Записать» → сразу выполнять demo-действия (см. §3).
4. Cmd + Ctrl + Esc или клик по чёрному квадрату в menubar для остановки.
5. Запись сохранится на Desktop как `Screen Recording YYYY-MM-DD ….mov`.

**Вариант B — ffmpeg:**
```bash
ffmpeg -f avfoundation -capture_cursor 1 -capture_mouse_clicks 1 \
       -framerate 30 -i "1:none" -t 25 \
       -vcodec libx264 -pix_fmt yuv420p Desktop/screen.mov
```
(Здесь `1:none` — индекс «1» это main display, проверь через `ffmpeg -f avfoundation -list_devices true -i ""`.)

---

## 3. Сценарии записи

### 3.1 Ролик 1 — Q&A с цитатами (~20 сек)

1. **Перед записью:** залогиниться как `ivanov@optics.demo`, открыть `/`, очистить чат («Очистить» в шапке).
2. **Старт записи.**
3. Сразу кликнуть в textarea внизу.
4. **Ввести медленно (или paste):** `Сформулируй принцип Ферма`
5. Enter.
6. Дождаться ответа (~15–20 с): сначала появятся step-badges, потом ответ с цитатами и source-panel.
7. **Подвести курсор** к pill `[1]` в ответе (без клика) → подсветится первая source-card в правой панели.
8. **Стоп записи.** ~22 с total.

**Проверка:** в записи должно быть видно (а) typing-steps крутящиеся, (б) inline `[N]` pills, (в) source-panel заполняется, (г) бейдж «Hard-gate verified».

### 3.2 Ролик 2 — Refusal-экран (~8 сек)

1. **Перед записью:** свежий чат (или продолжать прошлую сессию — refusal в любом случае яркий).
2. **Старт записи.**
3. **Ввести:** `Какова численность населения Москвы?`
4. Enter.
5. Через ~1.5 с появится refusal-screen с shield-иконкой, метриками, footnote.
6. **Стоп записи.** ~6 с total.

**Проверка:** видно (а) shield-иконку 96px, (б) заголовок «Hard-gate: запрос отклонён», (в) followup-suggestions внизу.

### 3.3 Ролик 3 — Self-check рубрика (~40 сек)

1. **Перед записью:** перейти на `/self-check`, поле «тема» пустое.
2. **Старт записи.**
3. **Ввести тему:** `Принципы Ферма и Гюйгенса` (топик 1.1 — стабильно работает; 2.x избегаем, см. honest finding в `rationale.md` §3.3).
4. Кликнуть «Начать».
5. Дождаться генерации (~25–35 с): step-badges крутятся.
6. Появится список 5 вопросов. **Кликнуть** правильные/случайные ответы для всех MC + ввести короткий текст в open-ended (например, `по принципу Ферма свет идёт по пути с экстремальным временем`).
7. Кликнуть «Отправить ответы».
8. Дождаться оценки (~10–15 с).
9. Появится результат с hero-score + rubric. Скролл вниз чтобы показать per-question breakdown.
10. **Стоп записи.** ~50 с total.

**Если 50 сек слишком много** — разбить на 2 части:
- 3a: `selfcheck-start.gif` — ввод темы → генерация → видны вопросы (~30 с)
- 3b: `selfcheck-result.gif` — submit → показ рубрики (~15 с)

---

## 4. Конвертация .mov → .gif

Запись macOS даёт `.mov`. Защитному слайду нужен `.gif` (универсально воспроизводится в любом софте + меньше).

```bash
# Установить ffmpeg, если ещё нет:
#   brew install ffmpeg

# Конвертировать (high quality, ~5–10 МБ для 20 сек):
ffmpeg -i "Screen Recording 2026-…-….mov" \
       -vf "fps=15,scale=1280:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
       -loop 0 docs/design/screencasts/01-qa-with-citations.gif

# Меньше / быстрее (640px wide, fps=12) — если файл слишком большой:
ffmpeg -i input.mov \
       -vf "fps=12,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
       -loop 0 output.gif
```

Целевой размер на ролик: **2–10 МБ**. Если получается больше — снизить fps до 10 или ширину до 480.

---

## 5. Проверка на защите

В день защиты:

1. **За 30 минут до:** открыть все 3 GIF локально, убедиться что воспроизводятся (Quick Look на macOS работает).
2. **На слайде:** поставить GIF как loop-gif (PowerPoint, Keynote, Google Slides — все поддерживают).
3. **В презентации:** держать GIF на слайде «технологический стек / RAG-pipeline» как иллюстрацию **рядом с цифрами M3** (`refusal_tnr=1.000`, `κ=1.000`).
4. **Если LLM упал в эфире:** говоришь «давайте посмотрим на запись прогона до защиты», переключаешься на слайд с GIF — видео работает без сети.

---

## 6. Артефакты в репозитории

После съёмки структура:

```
docs/design/screencasts/
  ├── 01-qa-with-citations.gif      (≤10 МБ)
  ├── 02-refusal-screen.gif         (≤3 МБ)
  ├── 03-selfcheck-rubric.gif       (≤15 МБ, или разбить на 3a + 3b)
  └── README.md  (опционально)
scripts/fixtures/
  ├── demo_qa_fermat_response.json     # реальный API-ответ для qa-fermat
  └── demo_refusal_moscow_response.json # реальный refusal-ответ
```

Фикстуры в `scripts/fixtures/` — исключительно reference: что **именно** возвращал API в момент захвата. Если в будущем потребуется добавить «replay mode» в чат (типа: подставлять заранее записанный ответ без LLM-вызова), эти JSON-ы — готовая основа.

---

## 7. Чек-лист перед съёмкой

- [ ] `./scripts/seed_demo.sh --no-verify` отработал без ошибок.
- [ ] `verify_demo_questions.py --quick` показал 2/2 PASS.
- [ ] Браузер в dark mode, окно 1440×900, DevTools закрыт.
- [ ] Залогинен `ivanov@optics.demo`.
- [ ] Чат очищен (если снимаем ролик 1 или 2).
- [ ] Все 3 ролика сняты в формате `.mov`.
- [ ] Каждый конвертирован в GIF ≤15 МБ.
- [ ] Файлы сохранены в `docs/design/screencasts/`.
- [ ] Открыты в Quick Look и проверены на воспроизведение.
