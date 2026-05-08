# Screenshot Gallery — для слайдов защиты

> ⚠️ **Этот документ устарел.**
>
> Актуальная аннотированная галерея переехала в
> [**`screenshots/after/README.md`**](screenshots/after/README.md) и теперь
> ссылается на реальные PNG-файлы.

---

## Почему переехала

Этот документ был создан в Фазе 1 (2026-05-07) **до** того, как скриншоты были фактически сняты. Имена файлов в нём (`02-chat-with-citations.png` и т.д.) не совпадают с теми, что лежат на диске после Фазы 6 (`02-chat-citations.png`). Сохранять две дивергирующих galleries рискованно.

В Фазе 6 скриншоты были захвачены систематически и помещены в [`screenshots/after/`](screenshots/after/). README в той папке — авторитетный источник:
- 8 P0 + 3 P1 разделов как walkthrough
- Каждый скриншот **inline** рядом со своим описанием (а не в preview-table dump'е)
- Тезис диссертации + demo-сценарий для каждого
- URL-helpers для одной-команды воспроизведения
- Pipeline захвата (osascript + screencapture + PIL crop)
- Чек-лист перед защитой

## Связанные документы

- [`screenshots/after/README.md`](screenshots/after/README.md) — **gallery с inline-скриншотами** (заменяет этот файл)
- [`demo-script.md`](demo-script.md) — пошаговый сценарий защиты, тоже с inline скриншотами
- [`demo-recording-protocol.md`](demo-recording-protocol.md) — инструкция по съёмке fallback-GIF
- [`rationale.md`](rationale.md) — обоснование UX-решений (для комиссии)

## Можно ли удалить этот файл

Можно, если в репозитории нет внешних ссылок на `docs/design/screenshot-gallery.md`. Этот файл оставлен как редирект-stub чтобы не сломать закладки коллег. После 1-2 спринтов без жалоб — удалить.
