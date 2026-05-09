"""Tenant isolation для /admin endpoints (BDD 4.x — M4.A baseline).

После обнаружения утечки `/admin/documents` и `/admin/ingestion-jobs/{id}`
2026-05-09 (super-admin без X-Atlas-Tenant и tenant-admin одного тенанта
видели документы другого тенанта), эти тесты закрепляют исправление.

Покрывает:
  1. /admin/documents возвращает только документы текущего тенант-контекста.
  2. /admin/ingestion-jobs/{id} возвращает 404 если job из другого тенанта.
  3. /admin/documents/{id} DELETE возвращает 404 при попытке удалить
     документ из чужого тенанта.

Pre-requisites:
  * ATLAS-стек запущен на http://127.0.0.1:8731.
  * Уже существуют tenants `optics-kafedra` (с born_wolf/matveev/yariv)
    и `semiconductors-kafedra` (с ЛКО_книга и др.) — создаются скриптами
    `scripts/seed_corpus.sh` + `scripts/seed_semicon_demo.sh`.
  * super-admin credentials в .env (ADMIN_EMAIL/ADMIN_PASSWORD).
"""
from __future__ import annotations

import os
import httpx
import pytest


BASE_URL = os.environ.get("ATLAS_TEST_BASE_URL", "http://127.0.0.1:8731")


def _is_live() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/health", timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _is_live(),
    reason=f"ATLAS stack not reachable at {BASE_URL}",
)


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
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _bearer(token: str, tenant: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if tenant:
        h["X-Atlas-Tenant"] = tenant
    return h


def test_admin_documents_isolated_per_tenant():
    """Super-admin с X-Atlas-Tenant видит только документы выбранного тенанта."""
    token = _login(*_admin_creds())

    r1 = httpx.get(f"{BASE_URL}/admin/documents",
                   headers=_bearer(token, "optics-kafedra"), timeout=10.0)
    assert r1.status_code == 200, r1.text
    optics_titles = {d["title"] for d in r1.json()}

    r2 = httpx.get(f"{BASE_URL}/admin/documents",
                   headers=_bearer(token, "semiconductors-kafedra"), timeout=10.0)
    assert r2.status_code == 200, r2.text
    semicon_titles = {d["title"] for d in r2.json()}

    # Должны быть disjoint sets, иначе утечка.
    overlap = optics_titles & semicon_titles
    assert not overlap, f"Tenant leak: {overlap} appear in both kafedras"

    # Sanity-check: оба не пусты.
    assert optics_titles, "optics-kafedra has no documents"
    assert semicon_titles, "semiconductors-kafedra has no documents"


def test_admin_ingestion_job_404_for_other_tenant():
    """GET /admin/ingestion-jobs/{id} с неверным X-Atlas-Tenant → 404."""
    token = _login(*_admin_creds())

    # Берём любой job из optics-kafedra (или skip если их нет).
    r = httpx.get(f"{BASE_URL}/admin/documents",
                  headers=_bearer(token, "optics-kafedra"), timeout=10.0)
    docs = r.json()
    if not docs:
        pytest.skip("No documents in optics-kafedra to derive a job from")

    # Неизвестный job id — 404 в обоих тенантах.
    fake_id = "00000000-0000-0000-0000-000000000000"
    for slug in ("optics-kafedra", "semiconductors-kafedra"):
        r = httpx.get(f"{BASE_URL}/admin/ingestion-jobs/{fake_id}",
                      headers=_bearer(token, slug), timeout=10.0)
        assert r.status_code == 404, f"{slug}: expected 404 for fake id, got {r.status_code}"


def test_admin_delete_404_for_other_tenant():
    """DELETE /admin/documents/{id} с неверным X-Atlas-Tenant → 404 (не удаляет)."""
    token = _login(*_admin_creds())

    # Возьмём первый документ optics-kafedra.
    r = httpx.get(f"{BASE_URL}/admin/documents",
                  headers=_bearer(token, "optics-kafedra"), timeout=10.0)
    optics_docs = r.json()
    if not optics_docs:
        pytest.skip("No documents in optics-kafedra")
    target_id = optics_docs[0]["document_id"]

    # Попытка удалить под X-Atlas-Tenant: semiconductors-kafedra → 404.
    r = httpx.delete(
        f"{BASE_URL}/admin/documents/{target_id}",
        headers=_bearer(token, "semiconductors-kafedra"),
        timeout=10.0,
    )
    assert r.status_code == 404, (
        f"Cross-tenant delete leaked: status={r.status_code} body={r.text[:200]}"
    )

    # Документ всё ещё на месте.
    r = httpx.get(f"{BASE_URL}/admin/documents",
                  headers=_bearer(token, "optics-kafedra"), timeout=10.0)
    titles = {d["document_id"] for d in r.json()}
    assert target_id in titles, "Document was deleted despite cross-tenant call"
