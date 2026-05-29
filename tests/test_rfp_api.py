"""
tests/test_rfp_api.py
=====================
Phase 5 PR-B1 exit criteria for the RFP-creation API.

Covers:
  B1 — POST /api/v1/rfps defaults (14-day deadline, autonomy_mode=auto_to_evaluate)
  B2 — POST /api/v1/rfps/{id}/vendors provisions drops/{rfp_id}/{vendor_id}/
  B3 — POST /api/v1/rfps/{id}/deadline returns 409 once status != open
  B4 — RBAC: only platform_admin / company_admin / department_admin /
       department_user can write; viewer is 403
  B5 — Phase 9 invariant: RFP creation writes nothing to
       user_departments / rfp_collaborators / approval_assignments
  B7 — existing /api/v1/evaluate/start manual-upload route still mounted

Uses FastAPI TestClient + dependency_overrides so we never have to
mint real JWTs. Cleans up its own fixture data on teardown.

Run:
    python -m pytest tests/test_rfp_api.py -v
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402

# Redirect drop folder to a test-scoped directory before the router is imported,
# so provision_drop_folder() picks it up via settings.platform.ingestion.drops_root.
settings.platform.ingestion.drops_root = str(Path(__file__).parent / "_drops_test")

from app.api.rfp_routes import router as rfp_router  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.auth.jwt import TokenData  # noqa: E402
from app.db.fact_store import get_engine  # noqa: E402

# Minimal app: only mount the router under test (avoid pulling in the
# full main.py and its heavy startup side-effects).
from fastapi import FastAPI  # noqa: E402

app = FastAPI()
app.include_router(rfp_router)


ORG_ID = str(uuid.uuid4())
OTHER_ORG_ID = str(uuid.uuid4())


def _user(role: str = "department_admin", org_id: str = ORG_ID) -> TokenData:
    return TokenData(
        email=f"{role}@meridian.test",
        org_id=org_id,
        role=role,
        dept_id="proc",
    )


@pytest.fixture
def as_admin():
    app.dependency_overrides[get_current_user] = lambda: _user("department_admin")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def as_viewer():
    app.dependency_overrides[get_current_user] = lambda: _user("viewer")
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def cleanup_rfp():
    """Yields a callback that deletes an rfp + cascading rows on teardown."""
    created: list[str] = []

    def _track(rfp_id: str) -> None:
        created.append(rfp_id)

    yield _track

    engine = get_engine()
    with engine.begin() as conn:
        for rid in created:
            conn.execute(sa.text("DELETE FROM event_log WHERE rfp_id = :r"), {"r": rid})
            conn.execute(sa.text("DELETE FROM ingestion_jobs WHERE rfp_id = :r"), {"r": rid})
            conn.execute(sa.text("DELETE FROM rfps WHERE rfp_id = :r"), {"r": rid})


# ── B1 ───────────────────────────────────────────────────────────────


def test_create_rfp_defaults(client, as_admin, cleanup_rfp):
    """B1 — create_rfp defaults to 14-day deadline + autonomy_mode=auto_to_evaluate."""
    from datetime import datetime, timezone

    response = client.post("/api/v1/rfps", json={"title": "IT Managed Services"})
    assert response.status_code == 201, response.text
    body = response.json()
    cleanup_rfp(body["rfp_id"])

    assert body["submission_status"] == "open"
    assert body["autonomy_mode"] == "auto_to_evaluate"

    deadline = datetime.fromisoformat(body["submission_deadline"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    diff_days = (deadline - now).total_seconds() / 86400
    assert 13.9 < diff_days < 14.1, f"deadline ~14d expected, got {diff_days:.3f}d"


# ── B2 ───────────────────────────────────────────────────────────────


def test_invite_vendor_provisions_folder(client, as_admin, cleanup_rfp, tmp_path):
    """B2 — invite_vendor creates DB row AND drops/{rfp_id}/{vendor_id}/ folder."""
    r = client.post("/api/v1/rfps", json={"title": "t"})
    rfp_id = r.json()["rfp_id"]
    cleanup_rfp(rfp_id)

    response = client.post(
        f"/api/v1/rfps/{rfp_id}/vendors",
        json={"vendor_id": "acme", "vendor_name": "Acme Corp"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    folder = Path(body["drop_folder"])
    assert folder.exists() and folder.is_dir()
    assert folder.name == "acme"
    assert folder.parent.name == rfp_id

    # Confirm DB row was written.
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT vendor_name FROM invited_vendors "
                "WHERE rfp_id = :r AND vendor_id = 'acme'"
            ),
            {"r": rfp_id},
        ).fetchone()
    assert row.vendor_name == "Acme Corp"


# ── B3 ───────────────────────────────────────────────────────────────


def test_deadline_locked_after_close(client, as_admin, cleanup_rfp):
    """B3 — set_deadline returns 409 once submission_status != open."""
    from datetime import datetime, timedelta, timezone

    r = client.post("/api/v1/rfps", json={"title": "t"})
    rfp_id = r.json()["rfp_id"]
    cleanup_rfp(rfp_id)

    # Bypass scheduler: flip status directly.
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE rfps SET submission_status = 'closed' WHERE rfp_id = :r"),
            {"r": rfp_id},
        )

    later = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    response = client.post(
        f"/api/v1/rfps/{rfp_id}/deadline",
        json={"submission_deadline": later},
    )
    assert response.status_code == 409, response.text


# ── B4 ───────────────────────────────────────────────────────────────


def test_rbac_rfp_create_viewer_forbidden(client, as_viewer):
    """B4.1 — viewer role gets 403 on POST /api/v1/rfps."""
    response = client.post("/api/v1/rfps", json={"title": "t"})
    assert response.status_code == 403


def test_rbac_cross_org_read_is_404(client, cleanup_rfp):
    """B4.2 — reading another org's RFP returns 404 (no existence leak)."""
    # Create as ORG_ID admin.
    app.dependency_overrides[get_current_user] = lambda: _user(org_id=ORG_ID)
    r = client.post("/api/v1/rfps", json={"title": "t"})
    rfp_id = r.json()["rfp_id"]
    cleanup_rfp(rfp_id)
    app.dependency_overrides.clear()

    # Read as different org admin.
    app.dependency_overrides[get_current_user] = lambda: _user(org_id=OTHER_ORG_ID)
    response = client.get(f"/api/v1/rfps/{rfp_id}")
    app.dependency_overrides.clear()
    assert response.status_code == 404


# ── B5 — Phase 9 invariant ───────────────────────────────────────────


def test_phase9_access_invariant_untouched(client, as_admin, cleanup_rfp):
    """B5 — creating an RFP + inviting a vendor must NOT write to access tables."""
    engine = get_engine()
    tables = ("user_departments", "rfp_collaborators", "approval_assignments")
    with engine.connect() as conn:
        before = {t: conn.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in tables}

    r = client.post("/api/v1/rfps", json={"title": "t"})
    rfp_id = r.json()["rfp_id"]
    cleanup_rfp(rfp_id)
    client.post(
        f"/api/v1/rfps/{rfp_id}/vendors",
        json={"vendor_id": "acme"},
    )

    with engine.connect() as conn:
        after = {t: conn.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in tables}

    assert before == after, f"access tables changed: {before} -> {after}"


# ── B7 — existing manual upload route still mounted ──────────────────


def test_existing_manual_upload_route_intact():
    """B7 — /api/v1/evaluate/start route still registered on main app."""
    # Import here to avoid heavyweight side-effects at module import.
    from app.main import app as main_app

    paths = {route.path for route in main_app.routes if hasattr(route, "path")}
    assert "/api/v1/evaluate/start" in paths, "manual upload route disappeared"
    assert "/api/v1/rfps" in paths, "new RFP routes not mounted"
