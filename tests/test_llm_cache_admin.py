"""
tests/test_llm_cache_admin.py
==============================
Phase 3 PR-B tests covering exit criteria 3.13 / 3.15 / context-var bypass.

  3.13 — `--no-cache` flag on smoke (env wiring; verified via llm_cache.enabled())
  3.15 — DELETE /api/v1/admin/llm-cache (bulk + by-model + by-cache_key + by-before)
  bonus — disable_for_current_context() flips enabled() to False for that context

Run:
    python -m pytest tests/test_llm_cache_admin.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.admin_routes import router as admin_router  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.auth.jwt import TokenData  # noqa: E402
from app.db.fact_store import get_engine  # noqa: E402
from app.providers import llm_cache  # noqa: E402


app = FastAPI()
app.include_router(admin_router)

ORG_ID = str(uuid.uuid4())


def _user(role: str = "department_admin", org_id: str = ORG_ID) -> TokenData:
    return TokenData(email=f"{role}@test", org_id=org_id, role=role, dept_id="proc")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def as_admin():
    app.dependency_overrides[get_current_user] = lambda: _user("department_admin")
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _restore_env():
    prev = os.environ.get("LLM_CACHE_ENABLED")
    yield
    if prev is None:
        os.environ.pop("LLM_CACHE_ENABLED", None)
    else:
        os.environ["LLM_CACHE_ENABLED"] = prev


def _seed_row(key: str, model: str = "gpt-4o", created_at_offset_min: int = 0) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO llm_response_cache
                    (cache_key, provider, model, response, created_at)
                VALUES
                    (:k, 'openai', :m, 'r', now() + :delta * interval '1 minute')
                """
            ),
            {"k": key, "m": model, "delta": created_at_offset_min},
        )


def _row_exists(key: str) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(
            sa.text("SELECT COUNT(*) FROM llm_response_cache WHERE cache_key = :k"),
            {"k": key},
        ).scalar()
    return n > 0


# ── bonus: disable_for_current_context() ─────────────────────────────


def test_disable_for_current_context_flips_enabled():
    assert llm_cache.enabled() is True

    async def _within():
        llm_cache.disable_for_current_context()
        assert llm_cache.enabled() is False

    asyncio.run(_within())

    # Outside the context, enabled() returns True again (root context untouched).
    assert llm_cache.enabled() is True


# ── 3.13 ─────────────────────────────────────────────────────────────


def test_env_disable_overrides_enabled():
    """3.13 — smoke --no-cache sets LLM_CACHE_ENABLED=false in the env."""
    os.environ["LLM_CACHE_ENABLED"] = "false"
    assert llm_cache.enabled() is False
    os.environ["LLM_CACHE_ENABLED"] = "true"
    assert llm_cache.enabled() is True


# ── 3.15 — Admin DELETE /llm-cache ───────────────────────────────────


def test_admin_purge_requires_filter(client, as_admin):
    """3.15 — calling DELETE with no filters returns 400."""
    response = client.delete("/api/v1/admin/llm-cache")
    assert response.status_code == 400


def test_admin_purge_by_cache_key(client, as_admin):
    k = f"test-{uuid.uuid4().hex}"
    _seed_row(k)
    assert _row_exists(k)

    response = client.delete(f"/api/v1/admin/llm-cache?cache_key={k}")
    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    assert not _row_exists(k)


def test_admin_purge_by_model(client, as_admin):
    keep_key = f"keep-{uuid.uuid4().hex}"
    drop1 = f"drop-{uuid.uuid4().hex}"
    drop2 = f"drop-{uuid.uuid4().hex}"
    _seed_row(keep_key, model="gpt-4o")
    _seed_row(drop1, model="gpt-3.5-turbo")
    _seed_row(drop2, model="gpt-3.5-turbo")

    response = client.delete("/api/v1/admin/llm-cache?model=gpt-3.5-turbo")
    assert response.status_code == 200
    assert response.json()["deleted"] >= 2  # may purge other test rows too
    assert _row_exists(keep_key)
    assert not _row_exists(drop1)
    assert not _row_exists(drop2)

    # Cleanup the keeper.
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("DELETE FROM llm_response_cache WHERE cache_key = :k"),
            {"k": keep_key},
        )


def test_admin_purge_by_before(client, as_admin):
    """3.15 — `before` cutoff drops rows created before the timestamp."""
    old_key = f"old-{uuid.uuid4().hex}"
    new_key = f"new-{uuid.uuid4().hex}"
    _seed_row(old_key, created_at_offset_min=-60)  # 1 hour ago
    _seed_row(new_key, created_at_offset_min=+60)  # 1 hour future

    cutoff = datetime.now(timezone.utc).isoformat()
    response = client.delete("/api/v1/admin/llm-cache", params={"before": cutoff})
    assert response.status_code == 200
    assert not _row_exists(old_key)
    assert _row_exists(new_key)

    # Cleanup.
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("DELETE FROM llm_response_cache WHERE cache_key = :k"),
            {"k": new_key},
        )


def test_admin_purge_rbac_viewer_forbidden(client):
    """Non-admin role gets 403."""
    app.dependency_overrides[get_current_user] = lambda: _user("viewer")
    response = client.delete("/api/v1/admin/llm-cache?cache_key=anything")
    app.dependency_overrides.clear()
    assert response.status_code == 403
