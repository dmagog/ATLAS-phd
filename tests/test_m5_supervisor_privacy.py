"""M5 — supervisor heatmap N-threshold + 404 anti-leak privacy posture.

Покрывает:
  * BDD 5.3 — heatmap is_below_threshold:
    - 0 студентов / 0 attempts → reason='n_students' или 'no_program'
    - 5 студентов / < 30 attempts → reason='n_attempts'
    - 5 студентов / ≥ 30 attempts → unblocked
  * BDD 5.5 — anti-leak 404 для supervisor:
    - student NOT opted-in → profile 404 + audit privacy.violation_attempt
    - student OPTED in → profile 200 + audit personal_data.access
    - non-existent UUID → 404 БЕЗ privacy.violation_attempt event
  * BDD 5.6 — student list visibility:
    - opted-in: email видно
    - не opted-in: email anonymized как «Аспирант #N»

Pre-requisites: ATLAS stack at http://127.0.0.1:8731.
"""
from __future__ import annotations

import os
import secrets
import string
import subprocess

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


def _psql(sql: str) -> str:
    """Execute SQL inside docker compose postgres, return stdout."""
    proc = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres",
         "psql", "-U", "atlas", "-d", "atlas", "--csv", "--tuples-only", "-c", sql],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True,
    )
    return proc.stdout.strip()


def _make_tenant(super_token: str) -> str:
    slug = _rand("test-sup-")
    r = httpx.post(
        f"{BASE_URL}/tenants",
        headers=_bearer(super_token),
        json={"slug": slug, "display_name": f"Test {slug}"},
        timeout=10.0,
    )
    assert r.status_code == 201, r.text
    return slug


def _issue_redeem(super_token: str, slug: str, role: str) -> tuple[str, str, str]:
    """Issue invite + redeem; return (token, email, user_id)."""
    r = httpx.post(
        f"{BASE_URL}/invites",
        headers=_bearer(super_token, {"X-Atlas-Tenant": slug}),
        json={"role": role},
        timeout=10.0,
    )
    assert r.status_code == 201, r.text
    code = r.json()["code"]
    email = f"{_rand(role[:3] + '-')}@example.com"
    r = httpx.post(
        f"{BASE_URL}/invites/{code}/redeem",
        json={"email": email, "password": "pw-12345", "consent_to_data_processing": True},
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], email, r.json()["user_id"]


def _upload_minimal_program(super_token: str, slug: str) -> str:
    """Upload a single-topic program; return that topic's external_id."""
    text = f"""---
program_version: v1.0
tenant_slug: {slug}
ratified_at: 2026-05-05
---

# Программа

## Раздел 1

### 1.1 Тема для пилота
**key_concepts:** концепт
"""
    r = httpx.post(
        f"{BASE_URL}/tenants/{slug}/program",
        headers=_bearer(super_token, {"X-Atlas-Tenant": slug}),
        json={"text": text},
        timeout=10.0,
    )
    assert r.status_code == 201, r.text
    return r.json()["topics"][0]["id"]  # uuid


def _seed_attempts(tenant_slug: str, topic_id: str, user_ids: list[str], n_per_user: int) -> None:
    """Insert N completed selfcheck_attempts per student via direct SQL."""
    tid = _psql(f"SELECT id FROM tenants WHERE slug = '{tenant_slug}';")
    assert tid, f"tenant {tenant_slug} not found"
    rows = []
    for uid in user_ids:
        for _ in range(n_per_user):
            rows.append(
                f"(gen_random_uuid(), '{uid}', 'тест', 'ru', 'completed', "
                f"NULL, NULL, '{{\"overall_score\": 4.0}}'::json, NOW(), NOW(), "
                f"'{tid}', '{topic_id}')"
            )
    if not rows:
        return
    sql = (
        "INSERT INTO selfcheck_attempts "
        "(id, user_id, topic, language, status, question_set, answers, evaluation, "
        "created_at, completed_at, tenant_id, topic_id) VALUES "
        + ",".join(rows) + ";"
    )
    _psql(sql)


# ─── BDD 5.3: heatmap N-threshold ─────────────────────────────────────────


def test_heatmap_below_threshold_no_program():
    sa_email, sa_pw = _admin_creds()
    super_token = _login(sa_email, sa_pw)
    slug = _make_tenant(super_token)
    sup_token, _, _ = _issue_redeem(super_token, slug, "supervisor")

    r = httpx.get(
        f"{BASE_URL}/tenants/{slug}/supervisor/heatmap",
        headers=_bearer(sup_token),
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_below_threshold"] is True
    # Without students AND program, gate is one of the two reasons.
    assert body["threshold_reason"] in ("n_students", "no_program"), body
    assert body["topics"] == []


def test_heatmap_below_threshold_attempts_short():
    """5 students but < 30 attempts → still below, reason='n_attempts'."""
    sa_email, sa_pw = _admin_creds()
    super_token = _login(sa_email, sa_pw)
    slug = _make_tenant(super_token)
    sup_token, _, _ = _issue_redeem(super_token, slug, "supervisor")
    topic_id = _upload_minimal_program(super_token, slug)

    student_uids = [_issue_redeem(super_token, slug, "student")[2] for _ in range(5)]
    _seed_attempts(slug, topic_id, student_uids, n_per_user=2)  # 5*2=10 < 30

    r = httpx.get(
        f"{BASE_URL}/tenants/{slug}/supervisor/heatmap",
        headers=_bearer(sup_token),
        timeout=10.0,
    )
    body = r.json()
    assert body["is_below_threshold"] is True, body
    assert body["threshold_reason"] == "n_attempts", body
    assert body["n_students_active"] == 5
    assert body["n_attempts_completed"] == 10


def test_heatmap_unblocks_at_threshold():
    """≥ 5 students and ≥ 30 attempts → unblocked."""
    sa_email, sa_pw = _admin_creds()
    super_token = _login(sa_email, sa_pw)
    slug = _make_tenant(super_token)
    sup_token, _, _ = _issue_redeem(super_token, slug, "supervisor")
    topic_id = _upload_minimal_program(super_token, slug)

    student_uids = [_issue_redeem(super_token, slug, "student")[2] for _ in range(5)]
    _seed_attempts(slug, topic_id, student_uids, n_per_user=6)  # 5*6=30

    r = httpx.get(
        f"{BASE_URL}/tenants/{slug}/supervisor/heatmap",
        headers=_bearer(sup_token),
        timeout=10.0,
    )
    body = r.json()
    assert body["is_below_threshold"] is False, body
    assert body["n_attempts_completed"] >= 30
    assert len(body["topics"]) >= 1


# ─── BDD 5.5: 404 anti-leak ──────────────────────────────────────────────


def test_profile_not_opted_in_returns_404_with_audit():
    sa_email, sa_pw = _admin_creds()
    super_token = _login(sa_email, sa_pw)
    slug = _make_tenant(super_token)
    sup_token, _, _ = _issue_redeem(super_token, slug, "supervisor")
    _, _, student_uid = _issue_redeem(super_token, slug, "student")

    # Default supervisor_visibility = anonymous-aggregate-only.
    r = httpx.get(
        f"{BASE_URL}/tenants/{slug}/supervisor/students/{student_uid}/profile",
        headers=_bearer(sup_token),
        timeout=10.0,
    )
    assert r.status_code == 404, (
        f"expected 404 (anti-leak), got {r.status_code} {r.text}"
    )

    # Audit must record privacy.violation_attempt.
    n = _psql(
        f"SELECT count(*) FROM audit_log WHERE action = 'privacy.violation_attempt' "
        f"AND target_id = '{student_uid}';"
    )
    assert int(n) >= 1, "privacy.violation_attempt not audited"


def test_profile_opted_in_returns_200_with_audit():
    sa_email, sa_pw = _admin_creds()
    super_token = _login(sa_email, sa_pw)
    slug = _make_tenant(super_token)
    sup_token, _, _ = _issue_redeem(super_token, slug, "supervisor")
    stu_token, stu_email, student_uid = _issue_redeem(super_token, slug, "student")

    # Student opts in.
    r = httpx.post(
        f"{BASE_URL}/me/visibility",
        headers=_bearer(stu_token),
        json={"visibility": "show-to-supervisor"},
        timeout=10.0,
    )
    assert r.status_code == 200, r.text

    r = httpx.get(
        f"{BASE_URL}/tenants/{slug}/supervisor/students/{student_uid}/profile",
        headers=_bearer(sup_token),
        timeout=10.0,
    )
    assert r.status_code == 200, r.text

    # Audit must record personal_data.access.
    n = _psql(
        f"SELECT count(*) FROM audit_log WHERE action = 'personal_data.access' "
        f"AND target_id = '{student_uid}';"
    )
    assert int(n) >= 1, "personal_data.access not audited"


def test_profile_unknown_student_returns_404_without_violation_audit():
    sa_email, sa_pw = _admin_creds()
    super_token = _login(sa_email, sa_pw)
    slug = _make_tenant(super_token)
    sup_token, _, _ = _issue_redeem(super_token, slug, "supervisor")

    fake_uuid = "00000000-0000-0000-0000-000000000000"
    r = httpx.get(
        f"{BASE_URL}/tenants/{slug}/supervisor/students/{fake_uuid}/profile",
        headers=_bearer(sup_token),
        timeout=10.0,
    )
    assert r.status_code == 404

    # No privacy.violation_attempt audit event for non-existent target —
    # there's nothing to leak.
    n = _psql(
        f"SELECT count(*) FROM audit_log WHERE action = 'privacy.violation_attempt' "
        f"AND target_id = '{fake_uuid}';"
    )
    assert int(n) == 0, "should not audit privacy violation for non-existent target"


# ─── BDD 5.6: student list anonymity ────────────────────────────────────


def test_student_list_anonymizes_non_opted_in():
    sa_email, sa_pw = _admin_creds()
    super_token = _login(sa_email, sa_pw)
    slug = _make_tenant(super_token)
    sup_token, _, _ = _issue_redeem(super_token, slug, "supervisor")

    # 1 opted in, 1 not.
    stu_in_token, stu_in_email, _ = _issue_redeem(super_token, slug, "student")
    httpx.post(
        f"{BASE_URL}/me/visibility",
        headers=_bearer(stu_in_token),
        json={"visibility": "show-to-supervisor"},
        timeout=10.0,
    ).raise_for_status()
    _issue_redeem(super_token, slug, "student")  # not opted-in

    r = httpx.get(
        f"{BASE_URL}/tenants/{slug}/supervisor/students",
        headers=_bearer(sup_token),
        timeout=10.0,
    )
    assert r.status_code == 200, r.text
    students = r.json()["students"]
    assert len(students) == 2

    visible = [s for s in students if s["visible"]]
    hidden = [s for s in students if not s["visible"]]
    assert len(visible) == 1, f"expected 1 visible (opted-in), got {len(visible)}"
    assert len(hidden) == 1, f"expected 1 hidden (anonymized), got {len(hidden)}"

    # Opted-in student's email must surface as display_name + must have student_id.
    assert visible[0]["display_name"] == stu_in_email
    assert visible[0]["student_id"]

    # Anonymized student must have no student_id and a placeholder name like
    # "Аспирант #N", and email must NOT leak via display_name.
    assert hidden[0]["student_id"] is None
    assert "Аспирант" in hidden[0]["display_name"]
    assert "@" not in hidden[0]["display_name"]
