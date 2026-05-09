#!/usr/bin/env bash
# seed_semicon_demo.sh — bootstrap второго пилотного тенанта
# `semiconductors-kafedra` (специальность 01.04.10 «Физика полупроводников»)
# для демонстрации multi-tenancy на защите.
#
# Что создаётся:
#   * tenant `semiconductors-kafedra`
#   * program v1.0-pilot из `corpus/semiconductors-kafedra/program.md` (6 топиков)
#   * 7 demo-пользователей (1 tenant-admin, 1 supervisor, 5 студентов)
#   * 5 PDF документов (digital-text only — Lect_opt, Lections_combined,
#     ЛКО_книга, Mikhnenko-exciton, Timofeev спектроскопия)
#
# Source PDFs are looked up в `Кандидатский экзамен/`, эта папка
# git-ignored (см. CLEANUP_MANIFEST.md).
#
# Использование:
#   ADMIN_EMAIL=... ADMIN_PASSWORD=... ./scripts/seed_semicon_demo.sh
#
# ИДЕМПОТЕНТЕН: повторный запуск пропускает уже существующие сущности.

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8731}"
SLUG="semiconductors-kafedra"
DISPLAY_NAME="Кафедра физики полупроводников"
DEMO_PASSWORD="${DEMO_PASSWORD:-demo}"
SOURCES_DIR="${SOURCES_DIR:-Кандидатский экзамен}"

ADMIN_EMAIL="${ADMIN_EMAIL:-}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"

if [ -z "$ADMIN_EMAIL" ] || [ -z "$ADMIN_PASSWORD" ]; then
  if [ -f .env ]; then
    set -a; source .env; set +a
  fi
fi
if [ -z "${ADMIN_EMAIL:-}" ] || [ -z "${ADMIN_PASSWORD:-}" ]; then
  echo "ADMIN_EMAIL / ADMIN_PASSWORD not set (попробуй .env)" >&2
  exit 2
fi

echo "==> Login as super-admin..."
TOKEN=$(curl -sf -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "==> Создаю tenant $SLUG..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/tenants" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"slug\":\"$SLUG\",\"display_name\":\"$DISPLAY_NAME\"}")
case "$HTTP_CODE" in
  201) echo "    ✓ создан" ;;
  409) echo "    = уже существует (ok)" ;;
  *)   echo "    ✗ unexpected status $HTTP_CODE"; exit 1 ;;
esac

echo "==> Загружаю программу..."
PROGRAM_PATH="corpus/$SLUG/program.md"
if [ ! -f "$PROGRAM_PATH" ]; then
  echo "    ✗ $PROGRAM_PATH не найден" >&2
  exit 1
fi
PROGRAM_BODY=$(python3 -c "import json; print(json.dumps({'text':open('$PROGRAM_PATH').read()}))")
PROG_CODE=$(curl -s -o /tmp/atlas_prog_resp.json -w "%{http_code}" -X POST "$BASE_URL/tenants/$SLUG/program" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "$PROGRAM_BODY")
if [ "$PROG_CODE" = "201" ]; then
  TOPICS=$(python3 -c "import json; print(len(json.load(open('/tmp/atlas_prog_resp.json'))['topics']))")
  echo "    ✓ программа активирована: $TOPICS топиков"
else
  echo "    ⚠ статус $PROG_CODE (возможно программа уже активна — ок для idempotent)"
fi

echo "==> Создаю demo-пользователей через invite/redeem..."
python3 - <<PY
import urllib.request, json, urllib.error, os
BASE = "$BASE_URL"; TOKEN = "$TOKEN"; SLUG = "$SLUG"; PWD = "$DEMO_PASSWORD"
def post(path, body, headers=None):
    h={"Content-Type":"application/json"}
    if headers: h.update(headers)
    r = urllib.request.Request(f"{BASE}{path}", data=json.dumps(body).encode(), headers=h, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')

ROSTER = [
    ("admin@semicon.demo",    "Кузнецов И. А.",  "tenant-admin"),
    ("nadezdin@semicon.demo", "Надеждин В. С.",  "supervisor"),
    ("orlov@semicon.demo",    "Орлов А. К.",     "student"),
    ("titova@semicon.demo",   "Титова Е. М.",    "student"),
    ("smirnov@semicon.demo",  "Смирнов П. Г.",   "student"),
    ("rybakov@semicon.demo",  "Рыбаков Д. Н.",   "student"),
    ("yakovlev@semicon.demo", "Яковлев С. И.",   "student"),
]
for email, name, role in ROSTER:
    code, body = post('/invites', {"role": role, "expires_in_days": 30},
        headers={"Authorization": f"Bearer {TOKEN}", "X-Atlas-Tenant": SLUG})
    if code != 201:
        print(f"    ✗ invite {email}: {code} {body}"); continue
    invite = body['code']
    code, body = post(f'/invites/{invite}/redeem', {
        "email": email, "password": PWD, "consent_to_data_processing": True
    })
    if code == 200:
        print(f"    ✓ {role:13s}  {email:30s}  {name}")
    elif code == 409:
        print(f"    = уже существует {email} (ok)")
    else:
        print(f"    ✗ redeem {email}: {code} {body}")

# Подмножеству студентов выставляем supervisor visibility = show
visible = ['orlov@semicon.demo', 'titova@semicon.demo', 'smirnov@semicon.demo']
for email in visible:
    code, body = post('/auth/login', {'email':email,'password':PWD})
    if code != 200: continue
    tok = body['access_token']
    post('/me/visibility', {'visibility':'show-to-supervisor'}, headers={"Authorization":f"Bearer {tok}"})
PY

echo "==> Загружаю PDF в $SLUG..."
upload_pdf() {
  local path="$1"
  if [ ! -f "$path" ]; then
    echo "    ⚠ skip (нет файла): $path"; return
  fi
  local resp
  resp=$(curl -sf -X POST "$BASE_URL/admin/ingestion-jobs" \
    -H "Authorization: Bearer $TOKEN" -H "X-Atlas-Tenant: $SLUG" \
    -F "files=@$path")
  if [ -n "$resp" ]; then
    local jid
    jid=$(echo "$resp" | python3 -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
    echo "    → отправлен: $(basename "$path")  job=$jid"
  else
    echo "    ✗ failed: $(basename "$path")"
  fi
}
upload_pdf "$SOURCES_DIR/вся инфа/ЛКО_книга.pdf"
upload_pdf "$SOURCES_DIR/вся инфа/Lect_opt.pdf"
upload_pdf "$SOURCES_DIR/Lections_combined.pdf"
upload_pdf "$SOURCES_DIR/вся инфа/Timofeev_Optic_sp.pdf"
upload_pdf "$SOURCES_DIR/Литература кандидатский/Mikhnenkoetal.-2015-Excitondiffusioninorganicsemiconductors.pdf"

echo
echo "✓ Семинар-кафедра $SLUG готова."
echo "  Демо логины (пароль: $DEMO_PASSWORD):"
echo "    admin@semicon.demo     — tenant-admin"
echo "    nadezdin@semicon.demo  — supervisor"
echo "    orlov@semicon.demo     — student (visible)"
echo
echo "Ingestion идёт в фоне; статус: GET /admin/ingestion-jobs/<job_id> с X-Atlas-Tenant: $SLUG"
