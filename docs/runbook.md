# Operations runbook

День-в-день операции для разработчика, поддерживающего пилот. Для аварийных сценариев — см. [`pilot/incident-runbook.md`](pilot/incident-runbook.md). Для разворачивания нового VPS — [`deployment/hetzner-setup.md`](deployment/hetzner-setup.md).

> Все команды предполагают `cd /home/atlas/atlas` (там, где `docker-compose.yml`).

## 1. Health check

```bash
curl -f https://atlas.<your-domain>/health
# → {"status":"ok"}
```

Если 502 / non-200 → переходи к §2 «Service restart».

Дополнительно вручную проверить контейнеры:
```bash
docker compose ps
# все три сервиса (app, embeddings, postgres) должны быть Up
```

## 2. Service restart

**Перезапуск только app (минимальное disruption):**
```bash
docker compose restart app
# downtime ~10-15s
```

**Полный рестарт (если что-то странное на нескольких уровнях):**
```bash
docker compose down
docker compose up -d
# downtime ~30-60s
```

После рестарта сразу проверь `/health` и пробный логин (см. §10).

## 3. Inspect logs by request_id

Каждый Q&A-запрос имеет `request_id` (UUID), который возвращается клиенту и логируется во всех структурированных событиях.

```bash
docker compose logs app | grep '"request_id": "<UUID>"' | python3 -m json.tool
```

Удобный one-liner — увидеть весь pipeline одного запроса:
```bash
RID="ebf008a8-1940-447f-9815-8775f2d8b768"
docker compose logs --since 24h app 2>&1 \
  | grep "$RID" \
  | jq -c '{ts: .timestamp, event: .event, state: .state, mode: .mode, top1: .top1_vscore, enough: .enough_evidence, reason: .reason}'
```

Что искать:
- `event: "qa_flow_start"` — пришёл запрос.
- `event: "retrieval_done"` — top1_vscore, chunks_above_threshold, enough_evidence.
- `event: "qa_flow_state", state: "REFUSAL_SENT"` — отказ + reason.
- `event: "qa_flow_error"` — exception.
- `event: "qa_flow_state", state: "RESPONSE_SENT"` — успешный ответ.

## 4. Ad-hoc backup перед изменением

Перед любой ручной модификацией БД (psql UPDATE, миграция) — снять снимок:
```bash
./scripts/pg_backup.sh ./tmp-backups
ls -la ./tmp-backups
# → atlas-YYYY-MM-DD-HHMMSS.sql.gz
```

`pg_backup.sh` подробнее: см. [`scripts/pg_backup.sh`](../scripts/pg_backup.sh) — это тот же скрипт, который крутится в cron'е, просто можно запустить вручную с другой `BACKUP_DIR`.

## 5. Restore from backup

**Полный restore из dump'а (destructive — все текущие данные потеряются):**

```bash
gunzip -c /home/atlas/backups/atlas-2026-05-04.sql.gz | \
    docker compose exec -T postgres psql -U atlas -d atlas
```

**Безопасный «boot a copy» вариант** — поднять временную БД в другом контейнере и сравнить:
```bash
docker run --rm -d --name atlas-temp -p 5433:5432 \
    -e POSTGRES_USER=atlas -e POSTGRES_PASSWORD=temp -e POSTGRES_DB=atlas \
    pgvector/pgvector:pg16
sleep 5
gunzip -c /home/atlas/backups/atlas-2026-05-04.sql.gz | \
    docker exec -i atlas-temp psql -U atlas -d atlas
psql -h localhost -p 5433 -U atlas -d atlas  # сверяй что нужно
docker stop atlas-temp
```

## 6. Image rollback

В `.env` зафиксирован тег image'а (`IMAGE_TAG=...`). Откат — proще всего через [`scripts/deploy.sh`](../scripts/deploy.sh) с `--tag`:

```bash
# 1. посмотреть, какие теги доступны
gh api /users/dmagog/packages/container/atlas-phd-app/versions \
    | jq '.[].metadata.container.tags'

# 2. откатиться на конкретный SHA — скрипт подменит IMAGE_TAG в .env,
#    подтянет образ, прогонит миграции и сделает up -d с health-check
./scripts/deploy.sh --no-pull --tag sha-abc1234
```

Ручной вариант (если deploy.sh недоступен):
```bash
vi .env  # IMAGE_TAG=sha-abc1234
docker compose pull app
docker compose up -d
curl -fsS http://localhost:8731/health
```

⚠️ Если за откатываемым релизом была применена migration — нужно либо `alembic downgrade` (если reversible), либо restore БД из dump'а на момент перед миграцией. См. §5.

## 7. Migration apply / rollback

**Применить новую миграцию (после `git pull`):**
```bash
# 1. snapshot БД (см. §4)
./scripts/pg_backup.sh ./tmp-backups

# 2. применить
docker compose exec -T app alembic upgrade head

# 3. перезапустить app (если миграция меняла схему, по которой бегает код)
docker compose restart app
```

**Откатить последнюю миграцию:**
```bash
docker compose exec -T app alembic downgrade -1
```
Если migration необратима (`downgrade` поднимает NotImplementedError) → restore из snapshot'а §5.

## 8. Add a tenant-admin / supervisor / student

Все три потока — через invite-flow tenant-admin'а (BDD 4.6).

**Самый быстрый путь — [`scripts/pilot_seed.py`](../scripts/pilot_seed.py)** (под super-admin'ом):
```bash
# 5 student invites одним запросом
python3 scripts/pilot_seed.py --invites 5

# 1 tenant-admin invite (методист)
python3 scripts/pilot_seed.py --invites 1 --role tenant-admin

# 1 supervisor invite (научрук)
python3 scripts/pilot_seed.py --invites 1 --role supervisor
```

Скрипт печатает markdown-табличку с кодами + ttl, готовую к рассылке.

**Ручной curl** (если скрипт недоступен):
```bash
TOKEN=$(curl -sS -X POST https://atlas.<domain>/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"email":"<tenant-admin>","password":"..."}' \
    | jq -r .access_token)

curl -sS -X POST https://atlas.<domain>/invites \
    -H "Authorization: Bearer $TOKEN" \
    -H "X-Atlas-Tenant: optics-kafedra" \
    -H 'Content-Type: application/json' \
    -d '{"role":"student"}'
# → {"code":"<32-char>","expires_at":"..."}
```

Передать `code` пользователю по любому защищённому каналу. Срок жизни — 7 дней (BDD 4.6).

Бутстрап первого super-admin'а делается автоматически из `.env` (`ADMIN_EMAIL`, `ADMIN_PASSWORD`) при старте сервиса.

## 9. Reset user password

В пилоте — manual через psql (UI пока без self-service flow):

```bash
# 1. сгенерировать новый hash
NEW_PW="<generate>"
HASH=$(docker compose exec -T app python3 -c "
from atlas.core.security import hash_password
print(hash_password('$NEW_PW'))
")

# 2. подставить в БД (audit обязательно!)
docker compose exec -T postgres psql -U atlas -d atlas <<SQL
UPDATE users SET hashed_password = '$HASH', jwt_version = jwt_version + 1
    WHERE email = '<email>';
INSERT INTO audit_log (action, target_type, target_id, details)
    VALUES ('user.password.reset', 'user',
        (SELECT id::text FROM users WHERE email = '<email>'),
        '{"reason": "manual reset by dev", "channel": "support"}'::jsonb);
SQL
```

Bump `jwt_version` обязателен — он инвалидирует все старые токены (BDD 7.5).

Передать new password через защищённый канал, попросить пользователя сменить через UI как только self-service появится.

## 10. Quick smoke after restart / deploy

```bash
# 1. health
curl -fsS https://atlas.<domain>/health

# 2. login + token
TOKEN=$(curl -sS -X POST https://atlas.<domain>/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"email":"<admin>","password":"<pw>"}' | jq -r .access_token)

# 3. простой Q&A на корпусе (должно вернуть status=success или refused, не error)
curl -sS -X POST https://atlas.<domain>/qa/message \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"message_text":"Запишите закон Малюса для интенсивности света через систему поляризатор-анализатор."}' \
    | jq '{status, request_id, has_citations: (.citations | length > 0)}'

# 4. метрики
python3 scripts/daily_metrics_report.py --window-hours 1
```

Если 1–4 проходят чисто — деплой здоров.

## 11. Daily metrics report

Запуск вручную:
```bash
python3 scripts/daily_metrics_report.py
python3 scripts/daily_metrics_report.py --tenant optics-kafedra
python3 scripts/daily_metrics_report.py --json   # для парсинга
```

Cron на хосте (по умолчанию настроен в [hetzner-setup.md §7](deployment/hetzner-setup.md)):
```cron
0 8 * * * cd /home/atlas/atlas && \
    python3 scripts/daily_metrics_report.py >> /home/atlas/reports/daily.log 2>&1
```

Поля `faithfulness_24h_judged` / `citation_accuracy_24h_judged` пока null — sampler ещё не подключён (M6.D, post-pilot decision).

## 12. Типовые user-сообщения

| Симптом | Действие |
|---|---|
| «Не могу залогиниться» | проверить email написан правильно; если invite ещё не redeemed — попросить redeem'ить через UI |
| «Получаю отказ на вопрос» | попросить request_id из UI → §3 → если top1_vscore < 0.55 — корпус не покрывает тему, эскалировать tenant-admin'у для добавления материала |
| «Хочу удалить аккаунт» | flow §8 в [`pilot/incident-runbook.md`](pilot/incident-runbook.md) — soft-delete + анонимизация |
| «Цитата ведёт не туда» | собрать request_id, проверить `citations` в trace; M3.B citation_accuracy метрика — кандидат в eval-set v3 |
| «Слишком медленно» | latency p50 ≤ 8s — норма; если > — `docker compose logs app` ищи timeout/retry; LLM provider может быть down |

## 13. Где что лежит

| Артефакт | Путь |
|---|---|
| docker-compose | [`docker-compose.yml`](../docker-compose.yml) |
| Postgres data | docker volume `atlas-phd_postgres_data` |
| Логи app | `docker compose logs app` (stdout/stderr) |
| Backups | `/home/atlas/backups/atlas-*.sql.gz` (cron) |
| `.env` | `/home/atlas/atlas/.env` (chmod 600) + копия в password manager |
| Migrations | [`alembic/versions/`](../alembic/versions/) |
| Eval set | [`eval/golden_set_v1/golden_set_v1.0.jsonl`](../eval/golden_set_v1/golden_set_v1.0.jsonl) |
| Eval reports | [`eval/results/`](../eval/results/) (включая M3-report.md) |

## 14. Когда эскалировать

| Условие | Куда |
|---|---|
| confirmed privacy leak | [`pilot/incident-runbook.md` §1](pilot/incident-runbook.md#privacy-incident) — 1 час до stop-the-bleed |
| `/health` down > 5 минут | [`pilot/incident-runbook.md` §2](pilot/incident-runbook.md#production-incident) |
| Аспирант запросил отзыв согласия | [`pilot/incident-runbook.md` §3 «Согласие отозвано»](pilot/incident-runbook.md#согласие-отозвано) |
| daily_metrics показывает просадку > 0.10 от baseline | weekly check-in — обсудить с tenant-admin'ом + смотреть logs |
| OOM на VPS | rescale CX22→CX32 ([hetzner-setup.md §troubleshooting](deployment/hetzner-setup.md#oom-на-appembeddings)) |
