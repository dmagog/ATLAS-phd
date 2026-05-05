"""M4.A — tenant read-only status enforcement.

Roadmap §M4.A чек-лист «Tenant status active ↔ read-only works».

Pre-requisites:
  * ATLAS stack at http://127.0.0.1:8731 (docker compose up).
  * Super-admin credentials in .env (ADMIN_EMAIL / ADMIN_PASSWORD).

Сценарий:
  1. super-admin создаёт свежий тенант (status=active по умолчанию).
  2. выпускает invite, студент redeem'ит → token.
  3. student → POST /me/visibility = 200 (active, можно писать).
  4. super-admin PATCH /tenants/{slug}/status → read-only.
  5. student → POST /me/visibility = 423 (locked).
  6. super-admin сам остаётся writable: POST /invites под X-Atlas-Tenant = 201.
  7. super-admin flip обратно → active.
  8. student → POST /me/visibility снова 200.
  9. super-admin → archived → student снова 423 (другое сообщение).

Cleanup best-effort (как в test_m4d_*).
"""
from __future__ import annotations

import os
import secrets
import string

import httpx
import pytest


BASE_URL = os.environ.get("ATLAS_TEST_BASE_URL", "http://127.0.0.1:8731")


def _is_live() -> bool:
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=2.0)
        return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _is_live(),
    reason=f"ATLAS stack not reachable at {BASE_URL} — skipping integration test",
)


def _rand(prefix: str, n: int = 6) -> str:
    return prefix + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(n))


def _admin_creds() -> tuple[str, str]:
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    if email and password:
        return email, password
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            kv = dict(
                line.strip().split("=", 1)
                for line in f
                if line.strip() and not line.startswith("#") and "=" in line
            )
            return kv["ADMIN_EMAIL"], kv["ADMIN_PASSWORD"]
    pytest.skip("super-admin credentials not available")


def _login(email: str, password: str) -> str:
    r = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
        timeout=10.0,
    )
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _bearer(token: str, extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if extra:
        h.update(extra)
    return h


def _set_status(super_token: str, slug: str, new_status: str) -> None:
    r = httpx.patch(
        f"{BASE_URL}/tenants/{slug}/status",
        headers=_bearer(super_token),
        json={"status": new_status},
        timeout=10.0,
    )
    assert r.status_code == 200, f"patch status {new_status}: {r.status_code} {r.text}"
    assert r.json()["status"] == new_status


def test_tenant_readonly_blocks_writes_for_bound_users():
    sa_email, sa_password = _admin_creds()
    super_token = _login(sa_email, sa_password)

    slug = _rand("test-ro-")
    student_email = f"{_rand('stu-ro-')}@example.com"
    student_password = "ro-test-pw-12345"

    # 1. create tenant
    r = httpx.post(
        f"{BASE_URL}/tenants",
        headers=_bearer(super_token),
        json={"slug": slug, "display_name": f"Test {slug}"},
        timeout=10.0,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "active"

    # 2. issue invite + redeem → student token
    r = httpx.post(
        f"{BASE_URL}/invites",
        headers=_bearer(super_token, {"X-Atlas-Tenant": slug}),
        json={"role": "student"},
        timeout=10.0,
    )
    assert r.status_code == 201, r.text
    invite_code = r.json()["code"]

    r = httpx.post(
        f"{BASE_URL}/invites/{invite_code}/redeem",
        json={
            "email": student_email,
            "password": student_password,
            "consent_to_data_processing": True,
        },
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    student_token = r.json()["access_token"]

    # 3. active → student write OK
    r = httpx.post(
        f"{BASE_URL}/me/visibility",
        headers=_bearer(student_token),
        json={"visibility": "show-to-supervisor"},
        timeout=10.0,
    )
    assert r.status_code == 200, f"active write blocked: {r.status_code} {r.text}"

    # 4. super-admin flips → read-only
    _set_status(super_token, slug, "read-only")

    # 5. student write → 423 Locked
    r = httpx.post(
        f"{BASE_URL}/me/visibility",
        headers=_bearer(student_token),
        json={"visibility": "anonymous-aggregate-only"},
        timeout=10.0,
    )
    assert r.status_code == 423, (
        f"read-only write should be 423 Locked, got {r.status_code} {r.text}"
    )
    assert "read-only" in r.text.lower(), r.text

    # 6. super-admin keeps writing (escape hatch)
    r = httpx.post(
        f"{BASE_URL}/invites",
        headers=_bearer(super_token, {"X-Atlas-Tenant": slug}),
        json={"role": "student"},
        timeout=10.0,
    )
    assert r.status_code == 201, (
        f"super-admin should bypass read-only, got {r.status_code} {r.text}"
    )

    # 7. flip back → active
    _set_status(super_token, slug, "active")

    # 8. student write OK again
    r = httpx.post(
        f"{BASE_URL}/me/visibility",
        headers=_bearer(student_token),
        json={"visibility": "show-to-supervisor"},
        timeout=10.0,
    )
    assert r.status_code == 200, (
        f"after flip back to active write should pass: {r.status_code} {r.text}"
    )

    # 9. archived → 423 with different message
    _set_status(super_token, slug, "archived")
    r = httpx.post(
        f"{BASE_URL}/me/visibility",
        headers=_bearer(student_token),
        json={"visibility": "anonymous-aggregate-only"},
        timeout=10.0,
    )
    assert r.status_code == 423, (
        f"archived write should be 423 Locked, got {r.status_code} {r.text}"
    )
    assert "archived" in r.text.lower(), r.text

    # restore status so tenant is in a sane state for cleanup janitors
    _set_status(super_token, slug, "active")


def test_unknown_status_rejected():
    """PATCH /tenants/{slug}/status with garbage value → 422."""
    sa_email, sa_password = _admin_creds()
    super_token = _login(sa_email, sa_password)

    slug = _rand("test-stval-")
    r = httpx.post(
        f"{BASE_URL}/tenants",
        headers=_bearer(super_token),
        json={"slug": slug, "display_name": f"Test {slug}"},
        timeout=10.0,
    )
    assert r.status_code == 201, r.text

    r = httpx.patch(
        f"{BASE_URL}/tenants/{slug}/status",
        headers=_bearer(super_token),
        json={"status": "frozen-banana"},
        timeout=10.0,
    )
    assert r.status_code == 422, f"garbage status should be 422, got {r.status_code}"
