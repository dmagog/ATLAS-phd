#!/usr/bin/env bash
# Seed sample corpus into ATLAS phd via the ingestion API.
# Usage: ./scripts/seed_corpus.sh
# Requires: ADMIN_EMAIL and ADMIN_PASSWORD set in environment or .env file

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8731}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-changeme}"
CORPUS_DIR="${CORPUS_DIR:-corpus}"

echo "==> Logging in as $ADMIN_EMAIL..."
TOKEN=$(curl -sf -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

if [ -z "$TOKEN" ]; then
  echo "ERROR: Failed to obtain auth token. Is the server running?"
  exit 1
fi

echo "==> Uploading corpus files from ./$CORPUS_DIR/ ..."
count=0
for f in "$CORPUS_DIR"/*.jsonl "$CORPUS_DIR"/*.pdf "$CORPUS_DIR"/*.txt "$CORPUS_DIR"/*.md; do
  [ -f "$f" ] || continue
  echo "    -> $f"
  curl -sf -X POST "$BASE_URL/admin/upload" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$f" > /dev/null
  count=$((count + 1))
done

if [ "$count" -eq 0 ]; then
  echo "No files found in $CORPUS_DIR/. Add PDF/JSONL/TXT/MD files and re-run."
  exit 1
fi

echo "==> $count file(s) submitted for ingestion."
echo "    Open http://127.0.0.1:8731/admin to monitor progress."
