#!/usr/bin/env bash
# pg_backup.sh — daily Postgres backup with rotation.
#
# Usage:
#   ./pg_backup.sh [BACKUP_DIR]
#
# Env (with sensible defaults):
#   BACKUP_DIR        — default /home/atlas/backups
#   RETENTION_DAYS    — default 7 (older .sql.gz removed)
#   POSTGRES_USER     — default atlas
#   POSTGRES_DB       — default atlas
#
# Cron suggestion:
#   0 4 * * * /home/atlas/pg_backup.sh > /home/atlas/backups/last_run.log 2>&1
#
# IMPORTANT: this script dumps via `docker compose exec` — it must run on the
# host where docker-compose.yml lives, with permissions to docker.

set -euo pipefail

# ─── Config ───────────────────────────────────────────────────────────────
BACKUP_DIR="${1:-${BACKUP_DIR:-/home/atlas/backups}}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
PG_USER="${POSTGRES_USER:-atlas}"
PG_DB="${POSTGRES_DB:-atlas}"

# Allow caller to override the compose project directory (where
# docker-compose.yml is). Default = parent of this script (repo root).
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
COMPOSE_DIR="${COMPOSE_DIR:-$(dirname "$SCRIPT_DIR")}"

# ─── Pre-flight ───────────────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"
TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
OUT_FILE="${BACKUP_DIR}/atlas-${TIMESTAMP}.sql.gz"

cd "$COMPOSE_DIR"

# Sanity: postgres container up?
if ! docker compose ps postgres 2>/dev/null | grep -qE "running|healthy"; then
    echo "[pg_backup] ERROR: postgres container is not running in $COMPOSE_DIR"
    exit 1
fi

# ─── Dump ─────────────────────────────────────────────────────────────────
echo "[pg_backup] $(date -Iseconds) starting dump → $OUT_FILE"

docker compose exec -T postgres pg_dump \
    -U "$PG_USER" -d "$PG_DB" \
    --no-owner --no-privileges \
    | gzip > "$OUT_FILE"

# Sanity check: file exists and non-trivial size.
if [ ! -s "$OUT_FILE" ] || [ "$(stat -c%s "$OUT_FILE" 2>/dev/null || stat -f%z "$OUT_FILE")" -lt 1000 ]; then
    echo "[pg_backup] ERROR: backup file looks empty/truncated: $OUT_FILE"
    rm -f "$OUT_FILE"
    exit 1
fi

SIZE="$(du -h "$OUT_FILE" | cut -f1)"
echo "[pg_backup] $(date -Iseconds) ok: $OUT_FILE ($SIZE)"

# ─── Rotate ───────────────────────────────────────────────────────────────
echo "[pg_backup] rotating: keeping last $RETENTION_DAYS days"
find "$BACKUP_DIR" -name 'atlas-*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -delete -print

# ─── Health summary ───────────────────────────────────────────────────────
COUNT="$(find "$BACKUP_DIR" -name 'atlas-*.sql.gz' -type f | wc -l | tr -d ' ')"
TOTAL="$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)"
echo "[pg_backup] retention: $COUNT files, total $TOTAL"
echo "[pg_backup] $(date -Iseconds) done"
