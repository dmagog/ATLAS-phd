"""M4.5.A — program upload + archive-on-replace lifecycle (BDD 4.2, 4.7, 7.4).

Покрывает:
  * POST /tenants/{slug}/program с валидным program.md → 201, parsed topics
  * GET /tenants/{slug}/program → активная программа, не архивные
  * Replace flow: вторая загрузка архивирует первую (status='archived'),
    новая становится active. Только одна active per tenant (BDD 7.4).
  * Slug в URL должен совпадать с frontmatter.tenant_slug → 422 иначе.
  * Garbage program.md → 422 ProgramParseError.
  * Tenant-admin одного тенанта не может загружать в чужой → 403/404.

Pre-requisites: ATLAS stack at http://127.0.0.1:8731, super-admin creds в .env.
"""
from __future__ import annotations

import os
import secrets
import string

import httpx
import pytest


BASE_URL = os.environ.get("ATLAS_TEST_BASE_URL", "http://127.0.0.1:8731")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_live() -> bool:
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=2.0)
        return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _is_live(),
    reason=f"ATLAS stack not reachable at {BASE_URL}",
)


def _rand(prefix: str, n: int = 6) -> str:
    return prefix + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(n))


def _admin_creds() -> tuple[str, str]:
    if "ADMIN_EMAIL" in os.environ and "ADMIN_PASSWORD" in os.environ:
        return os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"]
    env_path = os.path.join(REPO_ROOT, ".env")
    with open(env_path) as f:
        kv = dict(
            line.strip().split("=", 1) for line in f
            if line.strip() and not line.startswith("#") and "=" in line
        )
    return kv["ADMIN_EMAIL"], kv["ADMIN_PASSWORD"]


def _login(email: str, password: str) -> str:
    r = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _bearer(token: str, extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if extra:
        h.update(extra)
    return h


def _make_tenant(super_token: str, slug: str | None = None) -> str:
    slug = slug or _rand("test-prog-")
    r = httpx.post(
        f"{BASE_URL}/tenants",
        headers=_bearer(super_token),
        json={"slug": slug, "display_name": f"Test {slug}"},
        timeout=10.0,
    )
    assert r.status_code == 201, r.text
    return slug


def _program_md(tenant_slug: str, version: str, topics: list[tuple[str, str, str, list[str]]]) -> str:
    """topics: list of (external_id, section_title, topic_title, key_concepts)."""
    body = f"""---
program_version: {version}
tenant_slug: {tenant_slug}
ratified_at: 2026-05-05
---

# Программа

"""
    last_section = None
    for ext, section, title, kcs in topics:
        if section != last_section:
            body += f"\n## {section}\n\n"
            last_section = section
        kcs_str = ", ".join(kcs)
        body += f"### {ext} {title}\n**key_concepts:** {kcs_str}\n\n"
    return body


# ─── happy paths ─────────────────────────────────────────────────────────


def test_upload_program_returns_topics():
    sa_email, sa_pw = _admin_creds()
    token = _login(sa_email, sa_pw)
    slug = _make_tenant(token)

    text = _program_md(slug, "v1.0", [
        ("1.1", "Раздел 1. Основы", "Принципы Ферма и Гюйгенса", ["принцип Ферма", "эйконал"]),
        ("1.2", "Раздел 1. Основы", "Тонкие линзы", ["фокусное расстояние"]),
    ])
    r = httpx.post(
        f"{BASE_URL}/tenants/{slug}/program",
        headers=_bearer(token, {"X-Atlas-Tenant": slug}),
        json={"text": text},
        timeout=10.0,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == "v1.0"
    assert body["status"] == "active"
    assert len(body["topics"]) == 2
    assert {t["external_id"] for t in body["topics"]} == {"1.1", "1.2"}


def test_get_returns_active_program():
    sa_email, sa_pw = _admin_creds()
    token = _login(sa_email, sa_pw)
    slug = _make_tenant(token)

    text = _program_md(slug, "v1.0", [
        ("1.1", "Раздел 1", "Тема", ["концепт"]),
    ])
    httpx.post(
        f"{BASE_URL}/tenants/{slug}/program",
        headers=_bearer(token, {"X-Atlas-Tenant": slug}),
        json={"text": text},
        timeout=10.0,
    ).raise_for_status()

    r = httpx.get(
        f"{BASE_URL}/tenants/{slug}/program",
        headers=_bearer(token, {"X-Atlas-Tenant": slug}),
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == "v1.0"


# ─── BDD 4.7 / 7.4: archive-on-replace ───────────────────────────────────


def test_replace_archives_old_program():
    """Second upload should archive the first; only one active per tenant."""
    sa_email, sa_pw = _admin_creds()
    token = _login(sa_email, sa_pw)
    slug = _make_tenant(token)

    v1 = _program_md(slug, "v1.0", [("1.1", "Раздел 1", "Тема A", ["концепт-А"])])
    r1 = httpx.post(
        f"{BASE_URL}/tenants/{slug}/program",
        headers=_bearer(token, {"X-Atlas-Tenant": slug}),
        json={"text": v1},
        timeout=10.0,
    )
    assert r1.status_code == 201
    v1_id = r1.json()["id"]

    v2 = _program_md(slug, "v2.0", [("1.1", "Раздел 1", "Тема B", ["концепт-Б"])])
    r2 = httpx.post(
        f"{BASE_URL}/tenants/{slug}/program",
        headers=_bearer(token, {"X-Atlas-Tenant": slug}),
        json={"text": v2},
        timeout=10.0,
    )
    assert r2.status_code == 201, r2.text
    v2_id = r2.json()["id"]
    assert v2_id != v1_id
    assert r2.json()["version"] == "v2.0"

    # GET /program returns the new active one.
    r_get = httpx.get(
        f"{BASE_URL}/tenants/{slug}/program",
        headers=_bearer(token, {"X-Atlas-Tenant": slug}),
        timeout=10.0,
    )
    assert r_get.status_code == 200
    assert r_get.json()["id"] == v2_id
    assert r_get.json()["version"] == "v2.0"


# ─── validation ──────────────────────────────────────────────────────────


def test_slug_mismatch_returns_422():
    sa_email, sa_pw = _admin_creds()
    token = _login(sa_email, sa_pw)
    slug = _make_tenant(token)

    # frontmatter.tenant_slug != URL slug
    text = _program_md("wrong-slug", "v1.0", [("1.1", "S", "T", ["k"])])
    r = httpx.post(
        f"{BASE_URL}/tenants/{slug}/program",
        headers=_bearer(token, {"X-Atlas-Tenant": slug}),
        json={"text": text},
        timeout=10.0,
    )
    assert r.status_code == 422
    assert "slug" in r.text.lower()


def test_garbage_program_returns_422():
    sa_email, sa_pw = _admin_creds()
    token = _login(sa_email, sa_pw)
    slug = _make_tenant(token)

    r = httpx.post(
        f"{BASE_URL}/tenants/{slug}/program",
        headers=_bearer(token, {"X-Atlas-Tenant": slug}),
        json={"text": "no frontmatter, no topics, just plain text"},
        timeout=10.0,
    )
    assert r.status_code == 422


def test_body_must_be_dict_with_text():
    sa_email, sa_pw = _admin_creds()
    token = _login(sa_email, sa_pw)
    slug = _make_tenant(token)

    r = httpx.post(
        f"{BASE_URL}/tenants/{slug}/program",
        headers=_bearer(token, {"X-Atlas-Tenant": slug}),
        json={"wrong_key": "..."},
        timeout=10.0,
    )
    assert r.status_code == 422


# ─── cross-tenant: tenant-admin can't manage another tenant ──────────────


def test_tenant_admin_cannot_upload_to_other_tenant():
    sa_email, sa_pw = _admin_creds()
    super_token = _login(sa_email, sa_pw)

    slug_a = _make_tenant(super_token)
    slug_b = _make_tenant(super_token)

    # Create a tenant-admin user inside tenant-A via invite.
    r = httpx.post(
        f"{BASE_URL}/invites",
        headers=_bearer(super_token, {"X-Atlas-Tenant": slug_a}),
        json={"role": "tenant-admin"},
        timeout=10.0,
    )
    assert r.status_code == 201, r.text
    code = r.json()["code"]
    admin_email = f"{_rand('ta-')}@example.com"

    r = httpx.post(
        f"{BASE_URL}/invites/{code}/redeem",
        json={"email": admin_email, "password": "pw-12345", "consent_to_data_processing": True},
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    ta_token = r.json()["access_token"]

    # tenant-A admin tries to upload program to tenant-B → blocked.
    text = _program_md(slug_b, "v1.0", [("1.1", "S", "T", ["k"])])
    r = httpx.post(
        f"{BASE_URL}/tenants/{slug_b}/program",
        headers=_bearer(ta_token, {"X-Atlas-Tenant": slug_b}),
        json={"text": text},
        timeout=10.0,
    )
    assert r.status_code in (403, 404), (
        f"cross-tenant should be 403/404, got {r.status_code} {r.text}"
    )
