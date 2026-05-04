# Hetzner CX22 deployment — пилотный stack

Минимальный путь от чистого VPS до запущенного ATLAS, готового к пилоту. Hetzner CX22 (€5–7/мес) выбран как baseline (см. roadmap §M6.A): 2 vCPU, 4 ГБ RAM, 40 ГБ SSD — этого хватает на pilot 5–10 пользователей с одним тенантом × ≤ 10K chunks.

## Pre-requisites

- Hetzner Cloud аккаунт + API token.
- Domain под управлением (Cloudflare, Hetzner DNS, или любой другой).
- SSH-ключ на ноуте.
- Локально установлен `docker compose` для тестов.
- OpenRouter API key (или другой LLM provider).

## Step 1 — VPS

1. **Создать сервер** в Hetzner Cloud Console:
   - Type: CX22 (или CCX13, если есть бюджет — больше CPU/RAM).
   - Image: Ubuntu 24.04 LTS.
   - SSH key: ваш.
   - Datacenter: ближайший к пользователям (Helsinki, Falkenstein, Nuremberg для EU/RU).

2. **Залогиниться** и обновить:
   ```bash
   ssh root@<vps-ip>
   apt update && apt upgrade -y
   apt install -y docker.io docker-compose-v2 git ufw fail2ban
   systemctl enable --now docker
   ```

3. **Firewall** — открываем только нужное:
   ```bash
   ufw allow 22/tcp
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw enable
   ```

4. **Создать non-root user** (рекомендация — не работать под root):
   ```bash
   adduser atlas
   usermod -aG docker atlas
   usermod -aG sudo atlas
   ssh-copy-id atlas@<vps-ip>  # или вручную скопировать ~/.ssh/authorized_keys
   ```

   Дальше работаем под `atlas`.

## Step 2 — Code и .env

```bash
cd /home/atlas
git clone https://github.com/dmagog/ATLAS-phd.git atlas
cd atlas
cp .env.example .env
chmod 600 .env
```

Отредактировать `.env`:

```env
LLM_API_KEY=sk-or-v1-<your-real-key>
LLM_MODEL_ID=meta-llama/llama-3.3-70b-instruct:free  # или платная модель

POSTGRES_PASSWORD=<generate-strong-random>

JWT_SECRET=<generate-strong-random-32+chars>
ADMIN_EMAIL=<your-real-email>
ADMIN_PASSWORD=<generate-strong-random>

LOG_LEVEL=INFO
PILOT_TENANT_SLUG=optics-kafedra
VERIFIER_ENABLED=true
```

**Важно:** записать `JWT_SECRET`, `POSTGRES_PASSWORD`, `ADMIN_PASSWORD` в безопасное место (1Password / Bitwarden) — без них восстановление невозможно.

## Step 3 — Reverse proxy + HTTPS

Используем Caddy — автоматический Let's Encrypt:

```bash
sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:
```caddyfile
atlas.<your-domain> {
    reverse_proxy localhost:8731
    encode gzip
    log {
        output file /var/log/caddy/atlas.log
        format json
    }
}
```

DNS: A-запись `atlas` → `<vps-ip>` в DNS-провайдере.

```bash
sudo systemctl reload caddy
# Caddy автоматически получит TLS-сертификат через ACME.
```

## Step 4 — Запуск ATLAS

```bash
cd /home/atlas/atlas
docker compose up -d --build
```

Первый запуск: 5–10 мин на сборку embeddings image (torch + sentence-transformers).

Healthcheck:
```bash
curl -f https://atlas.<your-domain>/health
# → {"status":"ok"}
```

Если 502 — проверить, что app слушает на 8731 внутри контейнера и проброшен на хост:
```bash
docker compose ps
docker compose logs app | tail -50
```

## Step 5 — Бэкапы

```bash
mkdir -p /home/atlas/backups
cp /home/atlas/atlas/scripts/pg_backup.sh /home/atlas/pg_backup.sh
chmod +x /home/atlas/pg_backup.sh
crontab -e
# Добавить:
# 0 4 * * * /home/atlas/pg_backup.sh > /home/atlas/backups/last_run.log 2>&1
```

Тестовый прогон:
```bash
/home/atlas/pg_backup.sh
ls -la /home/atlas/backups/
```

Должен появиться `atlas-YYYY-MM-DD.sql.gz`. См. `scripts/pg_backup.sh` — ротация по 7 дней + manual offsite backup рекомендуется.

## Step 6 — Initial bootstrap

После первого запуска `seed_admin` создаёт super-admin user из `.env`. Проверка:
```bash
curl -X POST https://atlas.<your-domain>/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"<ADMIN_EMAIL>\",\"password\":\"<ADMIN_PASSWORD>\"}"
# → {"access_token":"...", "token_type":"bearer"}
```

Должен прийти JWT с role=super-admin.

Загружаем программу и материалы (см. `docs/welcome/tenant-admin.md`):
```bash
TOKEN=...
curl -X POST https://atlas.<your-domain>/tenants/optics-kafedra/program \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @- <<EOF
{"text": "$(cat corpus/optics-kafedra/program.md)"}
EOF
```

## Step 7 — Monitoring

Минимально:

1. **Hetzner monitoring** — встроенный (CPU, RAM, диск) уже работает в console.

2. **Sentry** (опционально для пилота):
   - Создать проект в Sentry.
   - Добавить в `.env`: `SENTRY_DSN=https://...`.
   - В коде: `import sentry_sdk; sentry_sdk.init(...)` в `app/main.py` (M6 enhancement).

3. **Daily metrics report** (ручной, минимально):
   ```bash
   /home/atlas/atlas/scripts/daily_metrics.sh > /home/atlas/daily-$(date +%Y%m%d).log
   ```
   Опционально → отправка в Telegram bot.

## Расходы на пилот (estimate)

| Item | Cost |
|---|---|
| Hetzner CX22 (8 weeks) | ~€10–14 |
| Domain (если новый) | €5–10 |
| OpenRouter free tier | €0 (с rate-limit risk) |
| OpenRouter paid (Llama 70B / GPT-4o-mini) | ~€10–30 за 8 недель пилота |
| **Total** | **€25–55** на 8 недель |

## Troubleshooting

### 502 после Caddy reload
- Проверить `docker compose ps` — все ли up.
- `docker compose logs app | tail -50` — может, упал на миграции.

### `alembic upgrade head` падает
- Если migration 0008 — проверить, что pgvector установлен (`docker compose logs postgres | grep pgvector`).
- Если 0007 — ручная проверка, не было ли rename'а до этого:
  ```sql
  SELECT slug FROM tenants;
  ```

### LLM 429 / timeout
- Free tier rate-limit. Решение — переключиться на paid model в `.env`:
  ```env
  LLM_MODEL_ID=anthropic/claude-3.5-sonnet  # или openai/gpt-4o-mini
  ```
- Re-deploy: `docker compose up -d`.

### OOM на app/embeddings
- CX22 (4 GB) — на грани. Если падает с ошибками памяти — escalate до CX32 (8 GB) — €11–13/мес. Без перезаливки данных:
  - Hetzner Console → Server → Rescale → CX32 → Reboot.
