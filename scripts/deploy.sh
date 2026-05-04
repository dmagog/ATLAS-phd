#!/usr/bin/env bash
# deploy.sh — manual production deploy для ATLAS на VPS.
#
# Roadmap §M6.A: «Деплой на VPS: разработчик руками: ssh prod && cd atlas &&
# git pull && docker-compose pull && docker-compose up -d (либо скрипт
# scripts/deploy.sh). Каждый деплой — осознанное решение разработчика.»
#
# Что делает (в порядке):
#   1. preflight: проверяет, что .env существует, нет uncommitted local diff'а
#   2. snapshot БД (через scripts/pg_backup.sh) — точка отката
#   3. git pull (опционально, см. --no-pull)
#   4. docker compose pull   — подтягивает app image с тегом из .env (IMAGE_TAG)
#   5. alembic upgrade head  — отдельным one-shot контейнером, ДО старта app
#   6. docker compose up -d  — рестарт сервисов
#   7. health-check + smoke   — /health, /auth/login, /qa/message
#   8. summary в stdout
#
# При ошибке миграции (5) — НЕ запускает up; показывает rollback-инструкцию.
# При ошибке health-check (7) — показывает последние 100 строк логов app.
#
# Usage:
#   ./scripts/deploy.sh                    # full deploy
#   ./scripts/deploy.sh --no-pull          # deploy с already-pulled .git tree
#   ./scripts/deploy.sh --tag sha-abc1234  # pin конкретный image tag
#   ./scripts/deploy.sh --skip-smoke       # без auth+qa smoke (только /health)

set -euo pipefail

# ─── Config ───────────────────────────────────────────────────────────────
REPO_DIR="${REPO_DIR:-/home/atlas/atlas}"
ENV_FILE="${ENV_FILE:-$REPO_DIR/.env}"
BACKUP_DIR="${BACKUP_DIR:-/home/atlas/backups}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8731/health}"

PULL=true
SMOKE=true
TAG_OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-pull) PULL=false; shift ;;
        --skip-smoke) SMOKE=false; shift ;;
        --tag) TAG_OVERRIDE="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "[deploy] unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$REPO_DIR"

log() { echo "[deploy $(date -Iseconds)] $*"; }
fail() { echo "[deploy ERROR] $*" >&2; exit 1; }

# ─── 1. Preflight ─────────────────────────────────────────────────────────
log "preflight"
[ -f "$ENV_FILE" ] || fail ".env not found at $ENV_FILE"

# uncommitted changes — это red flag (значит на проде что-то правили руками)
if [[ -n "$(git status --porcelain)" ]]; then
    log "WARNING: working tree dirty:"
    git status --short
    log "продолжаем — но проверь, что эти правки осознанные"
fi

# проверяем что docker / compose работают
docker compose ps >/dev/null 2>&1 || fail "docker compose не отвечает (запущен ли docker daemon?)"

# ─── 2. Pre-deploy backup ─────────────────────────────────────────────────
log "snapshot БД → $BACKUP_DIR (точка отката)"
if [ -x "$REPO_DIR/scripts/pg_backup.sh" ]; then
    BACKUP_DIR="$BACKUP_DIR" "$REPO_DIR/scripts/pg_backup.sh" "$BACKUP_DIR" \
        | tail -5 || fail "pg_backup.sh упал — деплой остановлен"
else
    log "WARNING: scripts/pg_backup.sh не найден — пропускаю snapshot"
fi

# ─── 3. Git pull ──────────────────────────────────────────────────────────
if $PULL; then
    log "git pull origin main"
    git fetch origin main --quiet
    BEFORE="$(git rev-parse HEAD)"
    git pull --ff-only origin main
    AFTER="$(git rev-parse HEAD)"
    if [[ "$BEFORE" == "$AFTER" ]]; then
        log "no new commits"
    else
        log "advanced: $BEFORE..$AFTER"
        git log --oneline "$BEFORE..$AFTER"
    fi
fi

# ─── 4. Pin image tag (optional) ──────────────────────────────────────────
if [[ -n "$TAG_OVERRIDE" ]]; then
    log "pin IMAGE_TAG=$TAG_OVERRIDE in $ENV_FILE"
    if grep -qE '^IMAGE_TAG=' "$ENV_FILE"; then
        sed -i.bak "s|^IMAGE_TAG=.*|IMAGE_TAG=$TAG_OVERRIDE|" "$ENV_FILE"
    else
        echo "IMAGE_TAG=$TAG_OVERRIDE" >> "$ENV_FILE"
    fi
fi

# ─── 5. Pull image ────────────────────────────────────────────────────────
log "docker compose pull (app)"
docker compose pull app || fail "compose pull упал — проверь GHCR auth и IMAGE_TAG"

# ─── 6. Migrations (one-shot, ДО старта app) ──────────────────────────────
log "alembic upgrade head (one-shot container)"
if ! docker compose run --rm app alembic upgrade head; then
    cat <<'ROLLBACK'
[deploy ERROR] alembic upgrade FAILED.

Сервис НЕ перезапускался — текущий running app остаётся на старой версии.
Варианты:
  1. Если миграция reversible: docker compose run --rm app alembic downgrade -1
     потом разобраться с migration в коде, новый деплой.
  2. Если необратимая: restore БД из ./tmp-backups (см. docs/runbook.md §5).
ROLLBACK
    exit 1
fi

# ─── 7. Restart services ──────────────────────────────────────────────────
log "docker compose up -d"
docker compose up -d --remove-orphans

# ─── 8. Health-check ──────────────────────────────────────────────────────
log "health-check (max 60s)"
for i in $(seq 1 30); do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
        log "health ok после $((i * 2))s"
        break
    fi
    if [ "$i" -eq 30 ]; then
        log "health-check НЕ прошёл за 60s. logs (last 100):"
        docker compose logs app --tail 100
        fail "deploy НЕ удался (health-check)"
    fi
    sleep 2
done

# ─── 9. Smoke (optional) ──────────────────────────────────────────────────
if $SMOKE; then
    log "smoke: login + Q&A"
    ADMIN_EMAIL=$(grep -E '^ADMIN_EMAIL=' "$ENV_FILE" | cut -d= -f2-)
    ADMIN_PASSWORD=$(grep -E '^ADMIN_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)
    BASE_URL="${BASE_URL:-http://localhost:8731}"
    TOKEN=$(curl -fsS -X POST "$BASE_URL/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
    [ -n "$TOKEN" ] || fail "smoke: /auth/login не вернул access_token"

    QA_RESP=$(curl -fsS -X POST "$BASE_URL/qa/message" \
        -H "Authorization: Bearer $TOKEN" \
        -H 'Content-Type: application/json' \
        -d '{"message_text":"Запишите закон Малюса для интенсивности света через систему поляризатор-анализатор."}')
    QA_STATUS=$(echo "$QA_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))")
    case "$QA_STATUS" in
        success|refused) log "smoke ok: /qa/message → status=$QA_STATUS" ;;
        *) log "smoke WARNING: /qa/message → status=$QA_STATUS (могут быть LLM-проблемы)" ;;
    esac
fi

# ─── 10. Summary ──────────────────────────────────────────────────────────
log "summary"
docker compose ps
log "deploy done. Если что-то идёт не так в течение часа — rollback по docs/runbook.md §6."
