#!/usr/bin/env bash
# M3 smoke-runbook: get JWT → run runner --only refusal → score → report.
# Полезен для быстрой проверки что pipeline работает end-to-end на проде/локали.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8731}"
ENV_FILE="${ENV_FILE:-.env}"
SET_PATH="${SET_PATH:-eval/golden_set_v1/golden_set_v1.0.jsonl}"
CFG_PATH="${CFG_PATH:-eval/configs/treatment.toml}"
# `${VAR-default}` (без `:`) — default только при unset; пустая строка → пусто
ONLY_FLAG="${ONLY_FLAG---only refusal}"

# Читаем admin creds из .env
ADMIN_EMAIL=$(grep -E '^ADMIN_EMAIL=' "$ENV_FILE" | cut -d= -f2-)
ADMIN_PASSWORD=$(grep -E '^ADMIN_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)

if [[ -z "$ADMIN_EMAIL" || -z "$ADMIN_PASSWORD" ]]; then
    echo "[smoke] нет ADMIN_EMAIL/ADMIN_PASSWORD в $ENV_FILE" >&2
    exit 1
fi

# Получаем JWT
echo "[smoke] login → $BASE_URL/auth/login"
TOKEN=$(curl -sS -X POST "$BASE_URL/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
    | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('access_token', ''))")

if [[ -z "$TOKEN" ]]; then
    echo "[smoke] не удалось получить JWT — проверьте /auth/login и admin creds" >&2
    exit 1
fi
echo "[smoke] got JWT: ${TOKEN:0:24}..."

# Прогон
TS=$(date -u +%Y%m%d_%H%M%S)
OUT_DIR="eval/results/run-smoke-$TS"
echo "[smoke] runner → $OUT_DIR"
ATLAS_EVAL_TOKEN="$TOKEN" python3 eval/runner.py \
    --set "$SET_PATH" \
    --config "$CFG_PATH" \
    --output "$OUT_DIR" \
    $ONLY_FLAG

# Скоринг (без LLM-judge для smoke — отдельно через --judge при необходимости)
echo "[smoke] score → $OUT_DIR/summary.json"
python3 eval/score.py --run "$OUT_DIR" --set "$SET_PATH" --skip-judge

echo "[smoke] done. summary:"
cat "$OUT_DIR/summary.json" | python3 -m json.tool
