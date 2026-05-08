# Screenshot Gallery — «после»

> **Версия:** 0.2 (2026-05-08, после Phase 6+UX-fixes)
> **Назначение:** аннотированная галерея скриншотов production-стенда
> для слайдов защиты. Каждый скриншот сопровождается тезисом
> диссертации, demo-сценарием и связью с шагом из
> [`demo-script.md`](../demo-script.md).

---

## Состояние

Скриншоты были сняты в текущем сеансе через `computer-use` MCP и
видны inline в conversation history. Файлы пока **не сохранены на
диск** в этой папке — `save_to_disk` MCP-инструмента пишет в
private-location недоступную из Bash-сэндбокса.

**Чтобы поместить файлы в эту папку**:
1. Открой conversation history Claude.
2. Найди по дате/содержанию скриншот из таблицы ниже.
3. Right-click → Save Image As → используй имя файла из колонки «file».
4. Сохрани в `docs/design/screenshots/after/`.

ИЛИ перезапусти захват: открой каждый URL по cheat-sheet ниже и сними
макOS Cmd+Shift+5 → выделить окно Chrome → запись → Сохранить как
`<filename>.png` в эту папку.

---

## P0 экраны (для основного demo-script)

| # | Файл | URL для воспроизведения | Тезис диссертации |
|---|---|---|---|
| 1 | `01-login.png` | `/login` (анонимный) | Brand-side с тремя ключевыми результатами M3 |
| 2 | `02-chat-citations.png` | `/?ask=Сформулируй принцип Ферма` (под ivanov@optics.demo) | RAG работает, источники проверяемы, inline citation pills `[N]` |
| 3 | `03-source-modal.png` | то же + `&open-source=1` | Drill-down: full snippet чанка retrieval'a с KaTeX |
| 4 | `04-refusal-screen.png` | `/?ask=Какова численность населения Москвы?` | **Центральный тезис M3:** hard-gate за <2s без LLM, `refusal_tnr=1.000` |
| 5 | `05-selfcheck-rubric.png` | `/self-check/history?open=<best-attempt-id>` | Hero score + rubric grid 40/30/20/10 + κ=1.000 badge |
| 6 | `06-supervisor-heatmap.png` | `/supervisor` (под vasiliev@optics.demo) | Privacy-aware кафедральный режим: 12 студентов × 6 топиков, 7/12 opted-in |
| 7 | `07-tenant-admin.png` | `/tenant-admin` (под admin@optics.demo) | Платформенность: программа + покрытие + invites + users |
| 8 | `08-eval-dashboard.png` | `/eval` (под super@optics.demo) | Главные цифры M3: refusal_tnr 1.000 / κ 1.000 / <2s + per-topic |

## P1 экраны (super-admin / новые из UX-итерации)

| # | Файл | URL | Что показывает |
|---|---|---|---|
| 9 | `09-tenants-list.png` | `/_/tenants` (super-admin) | Кафедры платформы: 1 реальная + onboarding-hint для добавления второй |
| 10 | `10-invites-page.png` | `/_/invites` (tenant-admin) | Dedicated invites view: hero-cards + 8 active codes + история |
| 11 | `11-create-invite-modal.png` | то же, click «+ Создать инвайт» | Модалка создания: role + max_uses + ttl_hours |

## P2 опциональные (на случай вопросов комиссии)

| # | Файл | URL | Когда использовать |
|---|---|---|---|
| 12 | `12-styleguide.png` | `/_/styleguide` (super-admin) | Если технический эксперт спросит о design-system |
| 13 | `13-history-list.png` | `/self-check/history` (любой student) | На вопрос «как студент видит свою историю» |
| 14 | `14-materials-page.png` | `/admin` (tenant-admin) | На вопрос «как загружаются учебники» |

---

## Live URL helpers (демо-готовые ссылки)

Все URL'ы используют `/_/demo-login?email=…` для instant-login без
ввода пароля. Helper закрыт в production (`app_env=production` → 404).

```
# Под student (ivanov@optics.demo)
http://127.0.0.1:8731/_/demo-login?email=ivanov@optics.demo&next=/?ask=Сформулируй%20принцип%20Ферма
http://127.0.0.1:8731/_/demo-login?email=ivanov@optics.demo&next=/?ask=Сформулируй%20принцип%20Ферма&open-source=1
http://127.0.0.1:8731/_/demo-login?email=ivanov@optics.demo&next=/?ask=Какова%20численность%20населения%20Москвы%3F
http://127.0.0.1:8731/_/demo-login?email=ivanov@optics.demo&next=/self-check/history?open=<attempt_id>

# Под supervisor (vasiliev@optics.demo)
http://127.0.0.1:8731/_/demo-login?email=vasiliev@optics.demo&next=/supervisor

# Под tenant-admin (admin@optics.demo)
http://127.0.0.1:8731/_/demo-login?email=admin@optics.demo&next=/tenant-admin
http://127.0.0.1:8731/_/demo-login?email=admin@optics.demo&next=/_/invites

# Под super-admin (super@optics.demo)
http://127.0.0.1:8731/_/demo-login?email=super@optics.demo&next=/eval
http://127.0.0.1:8731/_/demo-login?email=super@optics.demo&next=/_/tenants
```

Best showcase attempt_id для шага 5 (определи актуальный):
```bash
T=$(curl -s -X POST http://127.0.0.1:8731/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ivanov@optics.demo","password":"demo"}' | jq -r .access_token)

curl -s http://127.0.0.1:8731/self-check/history/list \
  -H "Authorization: Bearer $T" \
  | jq '[.[] | select(.status=="completed" and .overall_score >= 4.5)] | .[0].attempt_id'
```

---

## Чек-лист перед защитой

- [ ] `./scripts/seed_demo.sh` отработал → 14 пользователей, 92 attempts.
- [ ] `./scripts/verify_demo_questions.py --quick` PASS (1 qa + 1 refusal).
- [ ] Все 8 P0 скриншотов сохранены в эту папку.
- [ ] Открыты в Quick Look — выглядят чётко, текст читаем.
- [ ] (Optional) 3 GIF screencast'a сняты по [demo-recording-protocol.md](../demo-recording-protocol.md).
- [ ] Запасной план: если LLM лагает в эфире — переключиться на GIF.

---

## Changelog

- **0.2 (2026-05-08):** добавлены P0 экраны 9-11 (tenants list, invites page, create-invite modal) после UX-итерации. Обновлены URL helpers.
- **0.1 (2026-05-07):** первая версия с 7 P0 экранов.
