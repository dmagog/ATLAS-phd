#!/usr/bin/env python3
"""pilot_seed.py — bootstrap пилотного тенанта одной командой.

В день старта пилота tenant-admin делает несколько шагов: проверить, что
тенант существует, загрузить программу, выписать N invite-кодов для
аспирантов. Этот скрипт делает то же самое, но идемпотентно и в одну
команду.

Что делает:
    1. login как super-admin (creds из .env: ADMIN_EMAIL / ADMIN_PASSWORD)
    2. проверяет, что тенант существует (создаёт через POST /tenants, если
       нет; 409 Conflict — норма, тенант уже есть)
    3. загружает program.md, если файл указан (POST /tenants/{slug}/program)
       — старая программа архивируется автоматически (BDD 4.7)
    4. выписывает N invite-кодов с указанной ролью (POST /invites,
       X-Atlas-Tenant: <slug>)
    5. печатает в stdout табличку «email или индекс → invite-код → expires»
       — копи-паста готовая к отправке аспирантам

Запуск:
    # минимально — issue 5 student invites в optics-kafedra
    python3 scripts/pilot_seed.py --invites 5

    # с подгрузкой программы
    python3 scripts/pilot_seed.py \\
        --tenant optics-kafedra \\
        --display-name "Кафедра оптики (пилот)" \\
        --program corpus/optics-kafedra/program.md \\
        --invites 5

    # пригласить tenant-admin'a (методиста), не студентов
    python3 scripts/pilot_seed.py --invites 1 --role tenant-admin

    # JSON-режим для cron'а / автоматики
    python3 scripts/pilot_seed.py --invites 5 --json

Безопасность: скрипт ходит в /auth/login и /invites под super-admin'ом —
все действия идут в audit_log (invite.issue events). Коды показываются
в stdout, перенаправь в file с chmod 600 если нужно сохранить.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8731")
DEFAULT_TENANT = "optics-kafedra"


def read_env(env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        raise FileNotFoundError(f"env file not found: {env_file}")
    out = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
) -> tuple[int, dict]:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
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


def login(base_url: str, email: str, password: str) -> str:
    code, body = http_request(
        "POST",
        f"{base_url}/auth/login",
        body={"email": email, "password": password},
    )
    if code != 200 or "access_token" not in body:
        raise RuntimeError(f"/auth/login failed: {code} {body}")
    return body["access_token"]


def ensure_tenant(base_url: str, token: str, slug: str, display_name: str) -> str:
    """Create tenant if missing; return tenant_id either way."""
    code, body = http_request(
        "POST",
        f"{base_url}/tenants",
        headers={"Authorization": f"Bearer {token}"},
        body={"slug": slug, "display_name": display_name},
    )
    if code == 201:
        return body["id"], "created"
    if code == 409:
        # already exists — fetch it
        code2, body2 = http_request(
            "GET",
            f"{base_url}/tenants",
            headers={"Authorization": f"Bearer {token}"},
        )
        if code2 != 200:
            raise RuntimeError(f"GET /tenants failed: {code2} {body2}")
        for t in body2:
            if t["slug"] == slug:
                return t["id"], "already_exists"
        raise RuntimeError(f"tenant {slug} reported 409 but not in list")
    raise RuntimeError(f"POST /tenants failed: {code} {body}")


def upload_program(base_url: str, token: str, slug: str, program_text: str) -> dict:
    code, body = http_request(
        "POST",
        f"{base_url}/tenants/{slug}/program",
        headers={"Authorization": f"Bearer {token}"},
        body={"text": program_text},
    )
    if code != 201:
        raise RuntimeError(f"POST /tenants/{slug}/program failed: {code} {body}")
    return body


def issue_invite(
    base_url: str,
    token: str,
    slug: str,
    role: str,
    expires_in_days: int | None = None,
) -> dict:
    payload: dict = {"role": role}
    if expires_in_days is not None:
        payload["expires_in_days"] = expires_in_days
    code, body = http_request(
        "POST",
        f"{base_url}/invites",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Atlas-Tenant": slug,
        },
        body=payload,
    )
    if code != 201:
        raise RuntimeError(f"POST /invites failed: {code} {body}")
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env"))
    parser.add_argument("--tenant", default=DEFAULT_TENANT)
    parser.add_argument(
        "--display-name",
        default="Кафедра оптики (пилот)",
        help="используется только при создании тенанта",
    )
    parser.add_argument(
        "--program",
        default=None,
        help="путь к program.md (если указан — загружается; старая архивируется)",
    )
    parser.add_argument("--invites", type=int, default=0, help="сколько инвайтов выписать")
    parser.add_argument(
        "--role",
        default="student",
        choices=["student", "supervisor", "tenant-admin"],
        help="роль для всех инвайтов в этом запуске",
    )
    parser.add_argument(
        "--expires-in-days",
        type=int,
        default=None,
        help="срок жизни инвайта (default = 7 дней по серверу)",
    )
    parser.add_argument("--json", action="store_true", help="JSON-вывод вместо markdown-таблички")
    args = parser.parse_args(argv)

    env = read_env(Path(args.env_file))
    admin_email = env.get("ADMIN_EMAIL")
    admin_password = env.get("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        print("[pilot_seed] ADMIN_EMAIL / ADMIN_PASSWORD не найдены в .env", file=sys.stderr)
        return 2

    result: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "tenant_slug": args.tenant,
    }

    # 1. login
    token = login(args.base_url, admin_email, admin_password)

    # 2. tenant
    tenant_id, tenant_state = ensure_tenant(args.base_url, token, args.tenant, args.display_name)
    result["tenant_id"] = tenant_id
    result["tenant_state"] = tenant_state

    # 3. program (optional)
    if args.program:
        program_path = Path(args.program)
        if not program_path.exists():
            print(f"[pilot_seed] program file not found: {program_path}", file=sys.stderr)
            return 2
        prog = upload_program(args.base_url, token, args.tenant, program_path.read_text())
        result["program"] = {
            "id": prog.get("id"),
            "version": prog.get("version"),
            "topics_count": len(prog.get("topics", [])),
        }

    # 4. invites
    invites = []
    for i in range(args.invites):
        inv = issue_invite(
            args.base_url,
            token,
            args.tenant,
            args.role,
            expires_in_days=args.expires_in_days,
        )
        invites.append({
            "index": i + 1,
            "code": inv["code"],
            "role": inv["role"],
            "expires_at": inv["expires_at"],
        })
    result["invites"] = invites

    # 5. output
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # markdown / human-readable
    print(f"# Pilot seed — {result['started_at']}")
    print(f"- base_url: `{args.base_url}`")
    print(f"- tenant: `{args.tenant}` ({tenant_state})")
    if "program" in result:
        p = result["program"]
        print(f"- program: version `{p['version']}`, {p['topics_count']} topics loaded")
    print()
    if invites:
        print(f"## Invite codes ({len(invites)} × `{args.role}`)")
        print()
        print("| # | invite code | expires |")
        print("|---|---|---|")
        for inv in invites:
            print(f"| {inv['index']} | `{inv['code']}` | {inv['expires_at']} |")
        print()
        print("**Раздать аспирантам по защищённому каналу.** Срок — 7 дней по умолчанию.")
        print("Tenant-admin может посмотреть outstanding invites через `GET /invites` под")
        print("своим токеном.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
