#!/usr/bin/env bash
# seed_demo.sh — Phase 6.4 orchestrator.
#
# Поднимает локальный ATLAS-стенд в демо-готовое состояние одной командой:
#   1. Ensures docker compose up
#   2. Seeds 14 пользователей (1 tenant-admin + 1 supervisor + 12 студентов)
#   3. Seeds 40 self-check attempts с реалистичным распределением
#   4. (Optional) Quick-verify с одним qa + одним refusal
#
# Использование:
#   ./scripts/seed_demo.sh           # full seed + smoke verify
#   ./scripts/seed_demo.sh --no-verify
#   ./scripts/seed_demo.sh --full-verify  # +все qa + selfcheck (медленно)
#
# Идемпотентен: повторный запуск пропускает уже созданное.

set -euo pipefail

cd "$(dirname "$0")/.."

VERIFY_MODE="quick"  # quick | none | full
for arg in "$@"; do
    case "$arg" in
        --no-verify)   VERIFY_MODE="none" ;;
        --full-verify) VERIFY_MODE="full" ;;
        --help|-h)
            sed -n '3,18p' "$0" | sed 's/^# *//'
            exit 0 ;;
    esac
done

# ── 1. Docker up ──────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════"
echo " 1/4 Docker compose"
echo "═══════════════════════════════════════════════════════"
docker compose up -d 2>&1 | tail -5
echo "  Waiting for /health …"
for i in {1..30}; do
    if curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8731/health | grep -q "200"; then
        echo "  ✓ app ready"
        break
    fi
    sleep 2
done
echo

# ── 2. Users ──────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════"
echo " 2/4 Seed users"
echo "═══════════════════════════════════════════════════════"
docker compose exec -T app python3 /app/scripts/seed_demo_users.py
echo

# ── 3. Attempts ───────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════"
echo " 3/4 Seed self-check attempts"
echo "═══════════════════════════════════════════════════════"
docker compose exec -T app python3 /app/scripts/seed_demo_attempts.py | tail -10
echo

# ── 4. Verify ─────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════"
echo " 4/4 Verify (mode=$VERIFY_MODE)"
echo "═══════════════════════════════════════════════════════"
case "$VERIFY_MODE" in
    none)
        echo "  skipped (--no-verify)" ;;
    quick)
        docker compose exec -T app python3 /app/scripts/verify_demo_questions.py --quick ;;
    full)
        echo "  ⚠ full verification fires real LLM calls (~3-5 min, ~$0.05 OpenRouter)"
        docker compose exec -T app python3 /app/scripts/verify_demo_questions.py --include-selfcheck ;;
esac

echo
echo "═══════════════════════════════════════════════════════"
echo " ✓ Demo seed complete"
echo "═══════════════════════════════════════════════════════"
echo "  Login URL:        http://127.0.0.1:8731/login"
echo "  Demo accounts (password: demo):"
echo "    super-admin:    georgy-mamarin@mail.ru (your existing)"
echo "    tenant-admin:   admin@optics.demo"
echo "    supervisor:     vasiliev@optics.demo"
echo "    student:        ivanov@optics.demo"
echo
echo "  Pages to demo (in order):"
echo "    /login                  — brand-side + form (шаг 0)"
echo "    /        (chat)         — Q&A с цитатами   (шаг 1)"
echo "    /        (refusal)      — Hard-gate отказ   (шаг 2)"
echo "    /eval                   — eval dashboard    (шаг 3, super-admin)"
echo "    /self-check             — рубрика           (шаг 4)"
echo "    /supervisor             — heatmap           (шаг 5, supervisor)"
echo "    /tenant-admin           — программа         (шаг 6, tenant-admin)"
echo
echo "  Demo questions:           scripts/demo_questions.json"
echo "  Pre-defense verify:       scripts/verify_demo_questions.py"
