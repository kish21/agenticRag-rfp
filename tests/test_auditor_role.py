"""
tests/test_auditor_role.py
==========================
#55 (P0.12) — auditor role: read-only org-wide compliance access.

Exit criteria covered (see docs/dev/55.md):
  1. `auditor` is a valid JWT role (create/decode round-trip; in VALID_ROLES).
  2. An auditor token is BLOCKED from run-content endpoints:
       - POST /evaluate/start  -> 403
       - GET  /evaluate/list   -> {"runs": []}
  3. An auditor token CAN read the org-wide audit endpoints:
       - GET /api/v1/audit/access-log -> 200
       - GET /api/v1/audit/events     -> 200
  4. A non-audit-read role (department_user) gets 403 on those endpoints.
  5. Audit-read roles are config-driven (require_audit_read honours
     settings.product.rbac.audit_read_roles).
  6. Auditor is NOT in product.rfp_defaults.write_roles.

No live DB: the engine is monkeypatched. Uses FastAPI TestClient +
dependency_overrides so we never mint real JWTs.

Run:
    python -m pytest tests/test_auditor_role.py -v
"""
from __future__ import annotations

import io
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.auth.jwt import (  # noqa: E402
    TokenData, VALID_ROLES, create_access_token, decode_token,
)
from app.auth.rbac import require_audit_read  # noqa: E402
import app.api.audit_routes as audit_routes  # noqa: E402
from app.api.audit_routes import router as audit_router  # noqa: E402
from app.api.evaluation_routes import router as eval_router  # noqa: E402

ORG_ID = str(uuid.uuid4())


def _user(role: str) -> TokenData:
    return TokenData(email=f"{role}@meridian.test", org_id=ORG_ID, role=role, dept_id="proc")


# ── Fake DB engine (no Postgres needed) ──────────────────────────────────────
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


class _FakeEngine:
    def __init__(self, rows):
        self._rows = rows

    @contextmanager
    def connect(self):
        yield _FakeConn(self._rows)


@pytest.fixture
def app_under_test():
    app = FastAPI()
    app.include_router(audit_router)
    app.include_router(eval_router)
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app_under_test):
    return TestClient(app_under_test)


def _as(app, role: str):
    app.dependency_overrides[get_current_user] = lambda: _user(role)


# ── 1. JWT role validity ──────────────────────────────────────────────────────
def test_auditor_in_valid_roles():
    assert "auditor" in VALID_ROLES


def test_create_and_decode_auditor_token():
    tok = create_access_token(email="a@x.test", org_id=ORG_ID, role="auditor")
    data = decode_token(tok.access_token)
    assert data.role == "auditor"
    assert data.org_id == ORG_ID


# ── 5/6. Config-driven gate + write-role exclusion ───────────────────────────
def test_require_audit_read_allows_configured_roles():
    for role in settings.product.rbac.audit_read_roles:
        require_audit_read(_user(role))  # must not raise


def test_require_audit_read_blocks_other_roles():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        require_audit_read(_user("department_user"))
    assert exc.value.status_code == 403


def test_auditor_not_in_write_roles():
    assert "auditor" not in set(settings.product.rfp_defaults.write_roles)


def test_require_write_role_blocks_auditor_allows_operators():
    """The shared run-launch gate (start/confirm/re-evaluate/rerun) blocks
    read-only roles and admits every operational write role."""
    from fastapi import HTTPException
    from app.auth.rbac import require_write_role
    with pytest.raises(HTTPException) as exc:
        require_write_role(_user("auditor"))
    assert exc.value.status_code == 403
    for role in settings.product.rfp_defaults.write_roles:
        require_write_role(_user(role))  # must not raise


def test_audit_read_roles_default_includes_auditor():
    assert "auditor" in settings.product.rbac.audit_read_roles


# ── 2. Auditor blocked from run-content endpoints ────────────────────────────
def test_auditor_list_is_empty(app_under_test, client):
    _as(app_under_test, "auditor")
    resp = client.get("/api/v1/evaluate/list")
    assert resp.status_code == 200
    assert resp.json() == {"runs": []}


def test_auditor_cannot_start_run(app_under_test, client):
    _as(app_under_test, "auditor")
    resp = client.post(
        "/api/v1/evaluate/start",
        data={"rfp_title": "X", "department": "IT", "contract_value": "1000"},
        files={"rfp_file": ("rfp.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
    )
    assert resp.status_code == 403


def test_write_roles_still_allowed_to_start():
    """The #55 /start guard keys off product.rfp_defaults.write_roles, so the
    operator roles must remain in that set (guard must not over-block them).
    Asserted on the allow-set directly to keep the test hermetic (no DB)."""
    write_roles = set(settings.product.rfp_defaults.write_roles)
    assert {"platform_admin", "company_admin", "department_admin", "department_user"} <= write_roles


# ── 3/4. Audit endpoints: auditor allowed, department_user forbidden ─────────
def test_auditor_can_read_access_log(app_under_test, client, monkeypatch):
    rows = [(str(uuid.uuid4()), str(uuid.uuid4()), "cfo@x.test", "view_results",
             datetime.now(timezone.utc))]
    monkeypatch.setattr(audit_routes, "get_engine", lambda: _FakeEngine(rows))
    _as(app_under_test, "auditor")
    resp = client.get("/api/v1/audit/access-log")
    assert resp.status_code == 200
    body = resp.json()
    assert body["org_id"] == ORG_ID
    assert len(body["entries"]) == 1
    assert body["entries"][0]["action"] == "view_results"


def test_auditor_can_read_events(app_under_test, client, monkeypatch):
    rows = [(str(uuid.uuid4()), str(uuid.uuid4()), "human_override", "alice@x.test",
             None, {"reason": "x"}, datetime.now(timezone.utc))]
    monkeypatch.setattr(audit_routes, "get_engine", lambda: _FakeEngine(rows))
    _as(app_under_test, "auditor")
    resp = client.get("/api/v1/audit/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["events"][0]["event_type"] == "human_override"


def test_department_user_forbidden_on_access_log(app_under_test, client, monkeypatch):
    monkeypatch.setattr(audit_routes, "get_engine", lambda: _FakeEngine([]))
    _as(app_under_test, "department_user")
    resp = client.get("/api/v1/audit/access-log")
    assert resp.status_code == 403


def test_department_user_forbidden_on_events(app_under_test, client, monkeypatch):
    monkeypatch.setattr(audit_routes, "get_engine", lambda: _FakeEngine([]))
    _as(app_under_test, "department_user")
    resp = client.get("/api/v1/audit/events")
    assert resp.status_code == 403


def test_company_admin_can_read_access_log(app_under_test, client, monkeypatch):
    monkeypatch.setattr(audit_routes, "get_engine", lambda: _FakeEngine([]))
    _as(app_under_test, "company_admin")
    resp = client.get("/api/v1/audit/access-log")
    assert resp.status_code == 200


# ── #55 SSE within-org visibility fix ────────────────────────────────────────
# The /status + /stream SSE endpoints previously gated only on org membership,
# letting any same-org user (incl. auditor) subscribe to a run's progress.
# They now enforce require_run_access like every other per-run endpoint.
import app.api.evaluation_routes as eval_routes  # noqa: E402
import app.domain.visibility as visibility  # noqa: E402


def _foreign_run() -> dict:
    return {"run_id": str(uuid.uuid4()), "org_id": ORG_ID,
            "created_by_email": "someone_else@meridian.test"}


def test_auditor_blocked_from_status_stream(app_under_test, client, monkeypatch):
    monkeypatch.setattr(eval_routes, "_db_get_run", lambda rid, oid: _foreign_run())
    # auditor is not wide-role and matches no dept/collaborator/approver predicate
    monkeypatch.setattr(visibility, "can_view_run", lambda user, run_id: False)
    _as(app_under_test, "auditor")
    resp = client.get(f"/api/v1/evaluate/{uuid.uuid4()}/status")
    assert resp.status_code == 403


def test_non_collaborator_blocked_from_status_stream(app_under_test, client, monkeypatch):
    """A same-org department_user who is not owner/collaborator is also blocked
    (the core #55 within-org leak)."""
    monkeypatch.setattr(eval_routes, "_db_get_run", lambda rid, oid: _foreign_run())
    monkeypatch.setattr(visibility, "can_view_run", lambda user, run_id: False)
    _as(app_under_test, "department_user")
    resp = client.get(f"/api/v1/evaluate/{uuid.uuid4()}/status")
    assert resp.status_code == 403


def test_owner_passes_status_stream_access_check(monkeypatch):
    """require_run_access must NOT raise for the run's creator (fast-path)."""
    from app.auth.rbac import require_run_access
    owner = _user("department_user")
    run = {"run_id": str(uuid.uuid4()), "org_id": ORG_ID, "created_by_email": owner.email}
    require_run_access(owner, run)  # no exception == pass
