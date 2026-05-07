# Local pilot — запуск ATLAS на своей машине + сетевой доступ друзьям

Этот гайд для **самого простого пилота**: ATLAS крутится в Docker на твоём
ноутбуке (MacBook), 3–5 друзей подключаются по сети и пользуются как
аспиранты-тестировщики. Без VPS, без публичного домена, без LE-сертификатов.

Альтернатива (для production): [hetzner-setup.md](hetzner-setup.md). Этот же
гайд — для quick start и friend-pilot этапа.

> **Важно:** при выключении ноутбука сервис недоступен. Договорись с
> друзьями о временных слотах либо оставляй машину включённой на пилот.

## Pre-requisites

- macOS с Docker Desktop (4 ГБ RAM выделено в настройках Docker минимум).
- ~10 ГБ свободного места на диске (postgres-volume + embeddings cache).
- OpenRouter API key (платный — нужна стабильная LLM, см. M3-report v2.0).
- Решение, **как друзья будут подключаться**: LAN, Tailscale или туннель
  (см. §3 ниже).

## Step 1 — Запуск стэка

```bash
cd ~/Desktop/ATLAS-phd  # или где у тебя репо
git pull origin main

# .env уже должен существовать; проверь критичные поля
grep -E '^(LLM_API_KEY|LLM_MODEL_ID|JWT_SECRET|ADMIN_EMAIL|ADMIN_PASSWORD|POSTGRES_PASSWORD)=' .env

docker compose up -d --build
```

Первый запуск — ~5–10 мин (сборка embeddings image). Последующие — секунды.

Health check:
```bash
curl -fsS http://127.0.0.1:8731/health
# → {"status":"ok"}
```

## Step 2 — Bootstrap пилотного тенанта

`optics-kafedra` уже создан миграцией 0007. Программу `program.md` тоже
уже загружена (если запускал `pilot_seed.py` раньше — пропусти).

Если стартовая БД чистая, создай инвайты для тебя + друзей одной командой:

```bash
python3 scripts/pilot_seed.py \
    --tenant optics-kafedra \
    --display-name "Пилот ATLAS" \
    --program corpus/optics-kafedra/program.md \
    --invites 5
```

Скрипт напечатает markdown-табличку с 5 invite-кодами и сроком жизни 7 дней.
Скопируй её — будешь раздавать друзьям.

Если хочешь себе ещё и **tenant-admin** доступ (отдельно от super-admin'а
из `.env`):
```bash
python3 scripts/pilot_seed.py --invites 1 --role tenant-admin
```

## Step 3 — Сетевой доступ друзьям

Выбери **один** способ (по убыванию рекомендуемости).

### Вариант A — Tailscale (рекомендуется)

[Tailscale](https://tailscale.com) — частная VPN-сеть, твой ноут получает
адрес `100.x.x.x` который видят только участники tailnet'а. Идеально для
3–5 друзей: безопасно, без открытых портов наружу, без cloud-зависимости.

1. Поставь Tailscale на свой Mac, авторизуйся.
2. Узнай свой Tailscale-адрес: `tailscale ip -4` (что-то вроде `100.122.204.120`).
3. Друзья ставят Tailscale, ты их инвайтишь в свой tailnet.
4. Они открывают `http://<твой-tailscale-ip>:8731/` — работает.

Проверка с твоей же машины:
```bash
curl -fsS "http://$(tailscale ip -4):8731/health"
```

### Вариант B — LAN (если все в одной Wi-Fi)

Самый простой, но ограничен одной сетью.

1. Узнай LAN-IP: `ifconfig en0 | awk '/inet /{print $2}'` (типа `192.168.x.y`).
2. Friends → `http://192.168.x.y:8731/`.

Ограничения: только при одной Wi-Fi-сети, IP может смениться при reconnect.

### Вариант C — Cloudflare Tunnel (публичный URL без портов)

Если друзья в разных сетях и Tailscale — overkill:

```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8731
# Выведет URL вида https://random-words-12345.trycloudflare.com
```

Раздай этот URL — он публичный, но без auth у друзей будет invite-код.

⚠️ Каждый запуск генерирует новый URL. Для постоянного — `cloudflared tunnel
create` + named tunnel (требует cf-аккаунта).

### Вариант D — ngrok (quick & dirty)

```bash
brew install ngrok
ngrok http 8731
# https://xxxx.ngrok-free.app
```

То же что Cloudflare Tunnel, но free-tier ngrok'а имеет rate-limit на
~40 запросов/мин. Для 5-friend пилота должно хватить.

## Step 4 — Раздача доступа друзьям

Для каждого друга:
1. Скопируй invite-код из `pilot_seed.py` output.
2. Отправь сообщение по защищённому каналу (Telegram, Signal):

   > Привет! Я тестирую ATLAS — кандидатская подготовка по оптике.
   > Открой `http://<твой-адрес>:8731/login` (или Cloudflare/ngrok URL),
   > введи invite-код `<код>`, придумай пароль, прими согласие на обработку
   > учебных данных. Welcome-гайд: `<ссылка на docs/welcome/student.md>`
   > или у меня в телеге.

3. Друг логинится, начинает использовать. Его данные:
   - email + хеш пароля
   - selfcheck attempts, Q&A history
   - всё видно тебе как super-admin'у в логах
   - **personal-данные другим аспирантам не видны** (privacy by default)

## Step 5 — Daily ops

Каждый день проверяй:

```bash
# Health
curl -fsS http://127.0.0.1:8731/health

# Активность за сутки
python3 scripts/daily_metrics_report.py
# → markdown-таблица: users active 24h, self-check attempts, qa feedback,
#   privacy events. Чё в Telegram-чат пилотной группы — оптionально.

# Ad-hoc backup перед чем-то рискованным
./scripts/pg_backup.sh ./tmp-backups
```

Для постоянного backup'а можешь поставить cron на свой Mac:
```bash
# crontab -e
0 4 * * * cd ~/Desktop/ATLAS-phd && ./scripts/pg_backup.sh
```

(работает только если ноутбук включён в 4 утра).

## Step 6 — Если что-то ломается

Базовые шаги — в [`runbook.md`](../runbook.md):

| Симптом | Действие |
|---|---|
| Друг не может залогиниться | runbook §10 quick smoke; проверь invite не expired |
| 502 на `/qa/message` | `docker compose logs app | tail -50` — обычно LLM provider down |
| Хочешь увидеть лог конкретного запроса | runbook §3 — grep по `request_id` |
| Friend хочет удалить аккаунт | [`pilot/incident-runbook.md`](../pilot/incident-runbook.md) §3 «Согласие отозвано» |
| OOM на ноутбуке | Docker Desktop → Resources → больше RAM/CPU; либо CPU-throttle на embeddings |

Для **privacy-инцидентов** (даже подозрений) — обязательно:
[`pilot/incident-runbook.md`](../pilot/incident-runbook.md) §1, шаги
containment → assessment → notification.

## Step 7 — Завершение пилота

После 1–2 недель тестирования:

1. **Финальные метрики:**
   ```bash
   python3 scripts/daily_metrics_report.py --window-hours 720 > pilot-summary.md
   ```
2. **Дамп БД на память** (если будешь продолжать):
   ```bash
   ./scripts/pg_backup.sh ./pilot-final/
   ```
3. **Заполни** [`pilot/end-of-pilot-report-template.md`](../pilot/end-of-pilot-report-template.md).
4. Если останавливаешь сервис на длительно: `docker compose down` (volumes
   не удаляются, данные сохранятся для следующего запуска).

## Что НЕ покрывает этот гайд

- Production-grade SLA (для этого — Hetzner setup + Sentry + alerts).
- HTTPS-сертификаты для localhost (для friend-пилота не нужно — Tailscale/Cloudflare/ngrok дают TLS из коробки).
- Multi-tenant onboarding нескольких кафедр одновременно.
- Auto-failover, replication, geographic distribution.

Если пилот успешен и хочешь масштабироваться → переходи на
[hetzner-setup.md](hetzner-setup.md) для VPS-deploy.
