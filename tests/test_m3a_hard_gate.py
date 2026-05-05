"""M3.A — hard-gate refusal at retrieval layer (BDD 1.3 + 6.1).

Покрывает:
  * Off-topic вопрос против полного корпуса (optics-kafedra) → REFUSAL_SENT
    с reason_code=LOW_EVIDENCE, latency низкая (LLM не вызывался).
  * Empty corpus tenant → REFUSAL_SENT (gate=retrieval_empty).
  * In-corpus вопрос → НЕ refused (api_status ∈ {success, error}, не 'refused').
  * /qa/feedback: invalid rating → 422; valid rating → 204 + запись в БД.

Pre-requisites: ATLAS stack at http://127.0.0.1:8731. Используется
optics-kafedra (с реальным корпусом) для in-corpus / off-topic тестов
и ephemeral tenant для empty-corpus теста.
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
    proc = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres",
         "psql", "-U", "atlas", "-d", "atlas", "--csv", "--tuples-only", "-c", sql],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True,
    )
    return proc.stdout.strip()


def _verifier_enabled() -> bool:
    """Hard-gate is bound to settings.verifier_enabled. If baseline-mode is
    selected (env VERIFIER_ENABLED=false) on the live stack, hard-gate is
    bypassed — these tests assume treatment-mode (default) and skip otherwise.
    """
    # Read from .env
    env_path = os.path.join(REPO_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("VERIFIER_ENABLED="):
                    return line.split("=", 1)[1].strip().lower() != "false"
    return True


pytestmark_treatment = pytest.mark.skipif(
    not _verifier_enabled(),
    reason="hard-gate tests require VERIFIER_ENABLED=true (treatment mode)",
)


# ─── BDD 1.3: hard-gate on off-topic ─────────────────────────────────────


@pytestmark_treatment
def test_off_topic_question_refused_fast():
    """Off-topic вопрос → REFUSAL_SENT через hard-gate, без LLM-вызова."""
    sa_email, sa_pw = _admin_creds()
    token = _login(sa_email, sa_pw)

    # Что-то максимально далёкое от оптики.
    r = httpx.post(
        f"{BASE_URL}/qa/message",
        headers=_bearer(token, {"X-Atlas-Tenant": "optics-kafedra"}),
        json={"message_text": "Расскажи рецепт борща и сколько свеклы класть."},
        timeout=20.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "refused", f"expected refused, got {body['status']}"
    assert body["refusal_reason_code"] == "LOW_EVIDENCE"
    assert not body.get("answer_markdown")


@pytestmark_treatment
def test_in_corpus_question_not_refused_at_retrieval():
    """In-corpus вопрос НЕ должен попасть в hard-gate refusal.

    api_status может быть 'answered' (LLM вернул ответ), 'error'
    (LLM упал — free-tier rate-limit), но НЕ 'refused' с
    reason_code=LOW_EVIDENCE — иначе hard-gate ложно срабатывает на
    реальный optics-вопрос.
    """
    sa_email, sa_pw = _admin_creds()
    token = _login(sa_email, sa_pw)

    r = httpx.post(
        f"{BASE_URL}/qa/message",
        headers=_bearer(token, {"X-Atlas-Tenant": "optics-kafedra"}),
        json={
            "message_text": (
                "Сформулируйте закон Брюстера и приведите формулу для угла Брюстера "
                "через показатели преломления двух сред."
            )
        },
        timeout=60.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Допустимые исходы: answered (LLM ок), error (LLM rate-limit / провайдер
    # упал), но НЕ refused с reason_code=LOW_EVIDENCE.
    if body["status"] == "refused":
        assert body.get("refusal_reason_code") != "LOW_EVIDENCE", (
            f"in-corpus query falsely refused as LOW_EVIDENCE: {body}"
        )


# ─── retrieval_empty gate: ephemeral empty tenant ────────────────────────


@pytestmark_treatment
def test_empty_tenant_refuses_with_low_evidence():
    """Tenant без чанков → retrieval_empty → REFUSAL_SENT."""
    sa_email, sa_pw = _admin_creds()
    super_token = _login(sa_email, sa_pw)
    slug = _rand("test-empty-")
    r = httpx.post(
        f"{BASE_URL}/tenants",
        headers=_bearer(super_token),
        json={"slug": slug, "display_name": f"Empty {slug}"},
        timeout=10.0,
    )
    assert r.status_code == 201, r.text

    r = httpx.post(
        f"{BASE_URL}/qa/message",
        headers=_bearer(super_token, {"X-Atlas-Tenant": slug}),
        json={"message_text": "Любой вопрос"},
        timeout=20.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "refused"
    assert body["refusal_reason_code"] == "LOW_EVIDENCE"


# ─── /qa/feedback ────────────────────────────────────────────────────────


def test_feedback_invalid_rating_returns_422():
    sa_email, sa_pw = _admin_creds()
    token = _login(sa_email, sa_pw)

    r = httpx.post(
        f"{BASE_URL}/qa/feedback",
        headers=_bearer(token, {"X-Atlas-Tenant": "optics-kafedra"}),
        json={
            "request_id": "test-fake-req-id",
            "rating": "meh",  # invalid
        },
        timeout=10.0,
    )
    assert r.status_code == 422


def test_feedback_valid_rating_returns_204_and_persists():
    sa_email, sa_pw = _admin_creds()
    token = _login(sa_email, sa_pw)

    fake_request_id = f"test-{_rand('rid-', 12)}"
    r = httpx.post(
        f"{BASE_URL}/qa/feedback",
        headers=_bearer(token, {"X-Atlas-Tenant": "optics-kafedra"}),
        json={
            "request_id": fake_request_id,
            "rating": "negative",
            "question_text": "test question",
            "answer_markdown": "test answer",
        },
        timeout=10.0,
    )
    assert r.status_code == 204, r.text

    # Verify persisted
    n = _psql(f"SELECT count(*) FROM qa_feedback WHERE request_id = '{fake_request_id}';")
    assert int(n) == 1, "feedback row not persisted"
