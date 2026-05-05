#!/usr/bin/env python3
"""attach_corpus_by_keywords.py — auto-attach materials to topics by keyword hits.

В день старта пилота tenant-admin'у нужно привязать каждый материал к
топикам программы — без этого `coverage_chunks=0` для всех топиков, и:
  * Q&A не работает в topic-mode (нет evidence в нужном топике).
  * Self-check блокируется на coverage<K (BDD 4.5).
  * Supervisor heatmap не разблокируется (нужны и N≥5 и attempts≥30 И
    coverage хотя бы по одному топику).

Скрипт делает это эвристически: для каждой пары (документ × топик) считает,
в скольки чанках документа встречается хотя бы один key_concept топика
(ILIKE, case-insensitive, с подстрокой). Если match-count ≥ MIN_HITS
(default 3) — топик добавляется в attach-list для документа. Затем
делается POST /tenants/{slug}/materials/{id}/topics с накопленным списком,
триггеры M4.5.B автоматически наполнят chunk_topics и coverage_chunks.

Это **эвристика, не финальная разметка**. После прогона tenant-admin
должен пробежаться по docs/welcome/tenant-admin.md §«coverage report»
и точечно отвязать ложные match'и (или, наоборот, дополнить — если
key_concept написан в учебнике в нестандартном формате).

Запуск:
    python3 scripts/attach_corpus_by_keywords.py
    python3 scripts/attach_corpus_by_keywords.py --min-hits 5  # строже
    python3 scripts/attach_corpus_by_keywords.py --dry-run     # без attach
    python3 scripts/attach_corpus_by_keywords.py --tenant <slug>

Зависимости: только stdlib + docker (для psql), как у daily_metrics_report.py.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8731")
DEFAULT_TENANT = "optics-kafedra"
DEFAULT_MIN_HITS = 3


# ─── env / http helpers ──────────────────────────────────────────────────


def read_env(env_file: Path) -> dict[str, str]:
    out = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def http_request(method: str, url: str, *, headers=None, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode("utf-8")
            return resp.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8")
        try:
            return e.code, json.loads(payload)
        except json.JSONDecodeError:
            return e.code, {"detail": payload}


def login(base_url, email, password):
    code, body = http_request(
        "POST", f"{base_url}/auth/login", body={"email": email, "password": password}
    )
    if code != 200:
        raise RuntimeError(f"login failed: {code} {body}")
    return body["access_token"]


# ─── psql helper ─────────────────────────────────────────────────────────


def psql_scalar(query: str) -> str:
    proc = subprocess.run(
        [
            "docker", "compose", "exec", "-T", "postgres",
            "psql", "-U", os.environ.get("POSTGRES_USER", "atlas"),
            "-d", os.environ.get("POSTGRES_DB", "atlas"),
            "--csv", "--tuples-only", "-c", query,
        ],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    rows = [r for r in proc.stdout.strip().split("\n") if r]
    return rows[0] if rows else "0"


def count_chunk_hits(document_id: str, key_concepts: list[str]) -> int:
    """Count distinct chunks in `document_id` that match at least one key_concept (ILIKE)."""
    if not key_concepts:
        return 0
    # SQL injection safety: key_concepts come from программы, написанной
    # tenant-admin'ом — но всё равно экранируем кавычку. Подстановка через
    # ILIKE с %...%.
    pieces = []
    for kc in key_concepts:
        kc_escaped = kc.replace("'", "''")
        pieces.append(f"text ILIKE '%{kc_escaped}%'")
    where = " OR ".join(pieces)
    q = (
        f"SELECT count(DISTINCT id) FROM chunks "
        f"WHERE document_id = '{document_id}' AND ({where});"
    )
    return int(psql_scalar(q))


# ─── main ────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env"))
    parser.add_argument("--tenant", default=DEFAULT_TENANT)
    parser.add_argument("--min-hits", type=int, default=DEFAULT_MIN_HITS)
    parser.add_argument("--dry-run", action="store_true",
                        help="посчитать matches и распечатать, но не писать в БД")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    env = read_env(Path(args.env_file))
    token = login(args.base_url, env["ADMIN_EMAIL"], env["ADMIN_PASSWORD"])
    auth = {"Authorization": f"Bearer {token}", "X-Atlas-Tenant": args.tenant}

    # 1. fetch program (topics + key_concepts)
    code, prog = http_request("GET", f"{args.base_url}/tenants/{args.tenant}/program",
                              headers=auth)
    if code != 200 or not prog:
        print(f"[attach] no active program for {args.tenant}: {code}", file=sys.stderr)
        return 2
    topics = prog["topics"]  # [{id, external_id, key_concepts, ...}, ...]

    # 2. fetch documents
    code, docs = http_request("GET", f"{args.base_url}/admin/documents", headers=auth)
    if code != 200:
        print(f"[attach] /admin/documents failed: {code} {docs}", file=sys.stderr)
        return 2

    # 3. для каждого документа — найти подходящие топики
    plan = []
    for doc in docs:
        doc_id = doc["document_id"]
        matches = []
        for t in topics:
            hits = count_chunk_hits(doc_id, t["key_concepts"])
            if hits >= args.min_hits:
                matches.append({
                    "topic_external_id": t["external_id"],
                    "topic_title": t["title"],
                    "hits": hits,
                })
        plan.append({
            "document_id": doc_id,
            "title": doc["title"],
            "filename": doc["filename"],
            "chunk_count": doc["chunk_count"],
            "matches": matches,
        })

    # 4. apply (если не dry-run)
    if not args.dry_run:
        for p in plan:
            externals = [m["topic_external_id"] for m in p["matches"]]
            code, body = http_request(
                "POST",
                f"{args.base_url}/tenants/{args.tenant}/materials/{p['document_id']}/topics",
                headers=auth,
                body={"topic_external_ids": externals},
            )
            p["api_status"] = code
            if code != 200:
                p["api_error"] = body

    # 5. output
    if args.json:
        print(json.dumps({"min_hits": args.min_hits, "dry_run": args.dry_run, "plan": plan},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"# attach corpus by keywords — tenant={args.tenant}, min_hits={args.min_hits}")
    print(f"_dry_run={args.dry_run}_\n")
    for p in plan:
        print(f"## {p['title']} (`{p['filename']}`, {p['chunk_count']} chunks)")
        if not p["matches"]:
            print("- ⚠ нет матчей выше порога — материал НЕ привязан ни к одному топику")
        else:
            for m in p["matches"]:
                print(f"- ✓ {m['topic_external_id']} «{m['topic_title']}» — {m['hits']} chunk hits")
        if "api_status" in p:
            print(f"- API: {p['api_status']}")
            if "api_error" in p:
                print(f"- error: {p['api_error']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
