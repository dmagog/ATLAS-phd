# Screenshot Gallery — «после»

> Реальные скриншоты с production-стенда после Phase 6 seed.
> Снимки сделаны 2026-05-08 через `mcp__computer-use__screenshot`
> в браузере Chrome на DELL UP2516D (1456×819 viewport, dark mode).

## Как получить заново

После повторного `seed_demo.sh` + `seed_demo_real_attempts.py` + `seed_demo_showcase.py`
все экраны можно открыть через demo-helpers:

| URL | Скриншот |
|---|---|
| `/login` (анонимно) | login |
| `/_/demo-login?email=ivanov@optics.demo&next=/?ask=Сформулируй%20принцип%20Ферма` | chat-with-citations (auto-fires Q&A) |
| `/_/demo-login?email=ivanov@optics.demo&next=/?ask=Какова%20численность%20населения%20Москвы%3F` | refusal-screen |
| `/_/demo-login?email=ivanov@optics.demo&next=/self-check/history?open=<attempt_id>` | selfcheck-rubric (auto-opens detail modal) |
| `/_/demo-login?email=vasiliev@optics.demo&next=/supervisor` | supervisor-heatmap |
| `/_/demo-login?email=admin@optics.demo&next=/tenant-admin` | tenant-admin |
| `/_/demo-login?email=super@optics.demo&next=/eval` | eval-dashboard |

Все эти URL сами выполняют login (через POST /auth/login с password=`demo`),
сохраняют token в localStorage и редиректят на `?next=`. Идемпотентны.

## URL-helpers, добавленные в Phase 6 для скриншотов

* `GET /_/demo-login?email=<x>&next=<path>` — instant-login для @optics.demo юзеров.
  Возвращает 404 для остальных email'ов и в production.
* `GET /_/demo-seed-superadmin` — idempotent создаёт super@optics.demo super-admin.
  Используется один раз для bootstrap (без docker exec).
* `GET /?ask=<query>` — на chat-странице автоматически отправляет вопрос при загрузке.
* `GET /self-check/history?open=<attempt_id>` — auto-открывает detail-модалку.

Все эти пути закоммичены и удаляются скриптом cleanup перед production.

## Best attempt for selfcheck-rubric showcase

Ivanov, Интерференция света, score 4.7:
`f7e8eb07-30a4-4a8f-824f-444653c02868`

(Получить актуальный ID: GET /self-check/history/list под ivanov, фильтр `score >= 4.5`.)
