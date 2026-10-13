#!/usr/bin/env bash
# seed_ipma.sh — направление «Сертификация IPMA по управлению проектами»
# (тенант `ipma-pm`).
#
# Что создаётся:
#   * tenant `ipma-pm`
#   * программа v1.0 из `corpus/ipma-pm/program.md` (30 топиков по ICB4)
#   * 2 пользователя: admin@ipma.demo (tenant-admin), georgy@ipma.demo (student)
#   * корпус: ICB 4.0 том 1 + 8 лекций курса + конспекты аналитических техник
#     из `Сертификация IPMA/` (папка git-ignored: копирайт СОВНЕТ / ФУП)
#   * автопривязка материалов к топикам по key_concepts
#
# Использование:
#   ./scripts/seed_ipma.sh
#
# ADMIN_EMAIL / ADMIN_PASSWORD (super-admin) берутся из .env.
# ИДЕМПОТЕНТЕН: существующие тенант/пользователи пропускаются, повторная
# загрузка того же файла отклоняется ingestion'ом как DUPLICATE.

set -euo pipefail

cd "$(dirname "$0")/.."

BASE_URL="${BASE_URL:-http://127.0.0.1:8731}"
SLUG="ipma-pm"
DISPLAY_NAME="IPMA: управление проектами (ICB 4.0)"
DEMO_PASSWORD="${DEMO_PASSWORD:-demo}"
SOURCES_DIR="${SOURCES_DIR:-Сертификация IPMA}"

if [ -z "${ADMIN_EMAIL:-}" ] || [ -z "${ADMIN_PASSWORD:-}" ]; then
  if [ -f .env ]; then
    set -a; source .env; set +a
  fi
fi
if [ -z "${ADMIN_EMAIL:-}" ] || [ -z "${ADMIN_PASSWORD:-}" ]; then
  echo "ADMIN_EMAIL / ADMIN_PASSWORD not set (попробуй .env)" >&2
  exit 2
fi
if [ ! -d "$SOURCES_DIR" ]; then
  echo "Нет папки с материалами: $SOURCES_DIR" >&2
  exit 2
fi

export BASE_URL SLUG DISPLAY_NAME DEMO_PASSWORD SOURCES_DIR ADMIN_EMAIL ADMIN_PASSWORD

python3 - <<'PY'
import json, mimetypes, os, time, uuid, urllib.error, urllib.request
from pathlib import Path

BASE = os.environ["BASE_URL"]; SLUG = os.environ["SLUG"]
PWD = os.environ["DEMO_PASSWORD"]; SRC = Path(os.environ["SOURCES_DIR"])

def call(method, path, body=None, headers=None, raw=None, ctype="application/json"):
    h = {"Content-Type": ctype}
    h.update(headers or {})
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except json.JSONDecodeError:
            return e.code, {}

print("==> Login as super-admin...")
code, body = call("POST", "/auth/login",
                  {"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]})
assert code == 200, f"login failed: {code} {body}"
auth = {"Authorization": f"Bearer {body['access_token']}", "X-Atlas-Tenant": SLUG}

print(f"==> Тенант {SLUG}...")
code, body = call("POST", "/tenants", {"slug": SLUG, "display_name": os.environ["DISPLAY_NAME"]},
                  headers={"Authorization": auth["Authorization"]})
print({201: "    ✓ создан", 409: "    = уже существует (ok)"}.get(code, f"    ✗ {code} {body}"))
if code not in (201, 409):
    raise SystemExit(1)

print("==> Программа...")
text = Path(f"corpus/{SLUG}/program.md").read_text(encoding="utf-8")
code, body = call("POST", f"/tenants/{SLUG}/program", {"text": text}, headers=auth)
if code == 201:
    print(f"    ✓ активирована: {len(body['topics'])} топиков")
else:
    print(f"    ⚠ статус {code} (возможно, программа уже активна — ок для повторного запуска)")

print("==> Пользователи (invite → redeem)...")
for email, role in [("admin@ipma.demo", "tenant-admin"), ("georgy@ipma.demo", "student")]:
    code, body = call("POST", "/invites", {"role": role, "expires_in_days": 30}, headers=auth)
    if code != 201:
        print(f"    ✗ invite {email}: {code} {body}"); continue
    code, body = call("POST", f"/invites/{body['code']}/redeem",
                      {"email": email, "password": PWD, "consent_to_data_processing": True})
    print({200: f"    ✓ {role:13s} {email}", 409: f"    = уже существует {email}"}
          .get(code, f"    ✗ redeem {email}: {code} {body}"))

print(f"==> Загрузка материалов из «{SRC}»...")
files = sorted(p for p in SRC.iterdir() if p.suffix.lower() in (".pdf", ".docx"))
boundary = uuid.uuid4().hex
parts = []
for p in files:
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
        f'filename="{p.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + p.read_bytes() + b"\r\n")
payload = b"".join(parts) + f"--{boundary}--\r\n".encode()
code, body = call("POST", "/admin/ingestion-jobs", raw=payload, headers=auth,
                  ctype=f"multipart/form-data; boundary={boundary}")
assert code in (200, 201, 202), f"upload failed: {code} {body}"
job = body["job_id"]
print(f"    → {len(files)} файлов, job={job}; жду окончания индексации...")
while True:
    code, st = call("GET", f"/admin/ingestion-jobs/{job}", headers=auth)
    if st.get("status") in ("completed", "completed_with_errors", "failed"):
        break
    done = len(st.get("accepted_files", [])) + len(st.get("rejected_files", []))
    print(f"      {st.get('status')}: {done}/{len(files)}")
    time.sleep(10)
print(f"    статус: {st['status']}")
for f in st["accepted_files"]:
    print(f"    ✓ {f.get('filename')}  ({f.get('chunks_created', '?')} чанков)")
for f in st["rejected_files"]:
    reason = f.get("reason")
    mark = "=" if reason == "DUPLICATE" else "✗"
    print(f"    {mark} {f.get('filename')}: {reason}")
PY

echo "==> Привязка материалов к топикам по key_concepts..."
python3 scripts/attach_corpus_by_keywords.py --tenant "$SLUG"

echo
echo "✓ Направление $SLUG готово."
echo "  Вход: $BASE_URL/login (пароль: $DEMO_PASSWORD)"
echo "    georgy@ipma.demo  — student (чат, самопроверка)"
echo "    admin@ipma.demo   — tenant-admin (программа, материалы, покрытие)"
