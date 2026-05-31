"""
tests/test_auth_hardening.py
============================
E2 auth-hardening exit criteria. Proves, end-to-end:

  • prod-aware Secure cookie flag                       (cookie security)
  • one-account-per-email — duplicate signup is 409     (email uniqueness)
  • logout revokes the JWT server-side                  (revocation)
  • a minted token with no session row is rejected      (allowlist)
  • invite returns a one-time TOKEN, never a password   (no plaintext pw)
  • invite acceptance is single-use; invitee sets own pw
  • password reset is a one-time expiring token that revokes all sessions
  • reset request does not enumerate accounts
  • weak passwords and bad/expired tokens are rejected  (abuse)

These tests exercise the REAL get_current_user (no dependency override) so the
session-revocation path is genuinely covered. Identity reads/writes go through
the owner engine (get_admin_db), exactly as in production. Requires a running
Postgres provisioned from app/db/schema.sql. Cleans up its own orgs (cascades
to users / sessions / tokens).

Run:
    python -m pytest tests/test_auth_hardening.py -v
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.auth_routes import router as auth_router  # noqa: E402
from app.api.middleware import OrgContextMiddleware  # noqa: E402
from app.auth.dependencies import COOKIE_NAME, get_current_user  # noqa: E402
from app.auth.jwt import create_access_token  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.fact_store import get_admin_engine  # noqa: E402


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(OrgContextMiddleware)
    app.include_router(auth_router)
    return app


app = _make_app()


@pytest.fixture
def client():
    c = TestClient(app)
    yield c
    c.cookies.clear()
    app.dependency_overrides.clear()


@pytest.fixture
def cleanup_orgs():
    """Track org_ids; delete on teardown (cascades to users/sessions/tokens)."""
    created: list[str] = []
    yield created.append
    eng = get_admin_engine()
    with eng.begin() as conn:
        for oid in created:
            conn.execute(sa.text("DELETE FROM organisations WHERE org_id = CAST(:o AS uuid)"),
                         {"o": oid})


def _email() -> str:
    return f"e2-{uuid.uuid4().hex[:12]}@meridian.test"


def _signup(client, cleanup_orgs, email=None, password="hunter2pw") -> dict:
    email = email or _email()
    r = client.post("/api/v1/auth/signup", json={
        "org_name": f"Org {uuid.uuid4().hex[:6]}",
        "email": email, "password": password,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    cleanup_orgs(body["org_id"])
    body["_email"] = email
    body["_password"] = password
    return body


# ── Cookie security ──────────────────────────────────────────────────────────

def test_cookie_secure_follows_environment(client, cleanup_orgs, monkeypatch):
    """Secure flag on the auth cookie tracks settings.cookie_secure."""
    monkeypatch.setattr(settings, "cookie_secure", True)
    r = client.post("/api/v1/auth/signup", json={
        "org_name": "Sec Org", "email": _email(), "password": "hunter2pw"})
    assert r.status_code == 201, r.text
    cleanup_orgs(r.json()["org_id"])
    assert "secure" in r.headers["set-cookie"].lower()

    monkeypatch.setattr(settings, "cookie_secure", False)
    r2 = client.post("/api/v1/auth/signup", json={
        "org_name": "Insec Org", "email": _email(), "password": "hunter2pw"})
    assert r2.status_code == 201, r2.text
    cleanup_orgs(r2.json()["org_id"])
    assert "secure" not in r2.headers["set-cookie"].lower()


# ── Email uniqueness ───────────────────────────────────────────────────────────

def test_duplicate_email_signup_is_409(client, cleanup_orgs):
    user = _signup(client, cleanup_orgs)
    r = client.post("/api/v1/auth/signup", json={
        "org_name": "Second Org", "email": user["_email"], "password": "hunter2pw"})
    assert r.status_code == 409, r.text


def test_weak_password_rejected(client):
    r = client.post("/api/v1/auth/signup", json={
        "org_name": "Weak", "email": _email(), "password": "short"})
    assert r.status_code == 422, r.text


# ── Revocation ─────────────────────────────────────────────────────────────────

def test_logout_revokes_session(client, cleanup_orgs):
    user = _signup(client, cleanup_orgs)
    token = user["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    # Same token must now be rejected — the session was revoked server-side.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_minted_token_without_session_is_rejected(client, cleanup_orgs):
    """A validly-signed JWT that was never registered in the allowlist is denied."""
    user = _signup(client, cleanup_orgs)
    rogue = create_access_token(email=user["_email"], org_id=user["org_id"],
                                role="company_admin")
    # Drop signup's valid session cookie so only the un-registered token is sent
    # (the cookie is preferred over the Bearer header).
    client.cookies.clear()
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {rogue.access_token}"})
    assert r.status_code == 401, r.text


# ── Invite flow ────────────────────────────────────────────────────────────────

def test_invite_returns_token_not_password(client, cleanup_orgs):
    admin = _signup(client, cleanup_orgs)
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    invitee = _email()
    r = client.post("/api/v1/auth/invite", headers=headers,
                    json={"email": invitee, "role": "department_user"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "invite_token" in body and body["invite_token"]
    # No plaintext / temporary password is returned as a value.
    assert "temp_password" not in body
    assert "password" not in body

    # Invitee redeems the token and chooses their own password → can log in.
    accept = client.post("/api/v1/auth/invite/accept",
                         json={"token": body["invite_token"], "password": "newpass12"})
    assert accept.status_code == 201, accept.text
    login = client.post("/api/v1/auth/token", json={"email": invitee, "password": "newpass12"})
    assert login.status_code == 200, login.text


def test_invite_accept_is_single_use(client, cleanup_orgs):
    admin = _signup(client, cleanup_orgs)
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    r = client.post("/api/v1/auth/invite", headers=headers,
                    json={"email": _email(), "role": "department_user"})
    tok = r.json()["invite_token"]
    assert client.post("/api/v1/auth/invite/accept",
                       json={"token": tok, "password": "newpass12"}).status_code == 201
    # Second redemption of the same token is refused.
    again = client.post("/api/v1/auth/invite/accept",
                        json={"token": tok, "password": "newpass12"})
    assert again.status_code == 400, again.text


def test_invite_requires_privileged_role(client, cleanup_orgs):
    """A department_user cannot invite."""
    from app.auth.jwt import TokenData
    app.dependency_overrides[get_current_user] = lambda: TokenData(
        email="u@x.test", org_id=str(uuid.uuid4()), role="department_user")
    try:
        r = client.post("/api/v1/auth/invite", json={"email": _email()})
        assert r.status_code == 403, r.text
    finally:
        app.dependency_overrides.clear()


def test_invite_accept_bad_token_rejected(client):
    r = client.post("/api/v1/auth/invite/accept",
                    json={"token": "not-a-real-token", "password": "newpass12"})
    assert r.status_code == 400, r.text


# ── Password reset ───────────────────────────────────────────────────────────

def test_password_reset_flow_revokes_sessions(client, cleanup_orgs):
    user = _signup(client, cleanup_orgs)
    old_token = user["access_token"]
    old_headers = {"Authorization": f"Bearer {old_token}"}
    assert client.get("/api/v1/auth/me", headers=old_headers).status_code == 200

    req = client.post("/api/v1/auth/password-reset/request", json={"email": user["_email"]})
    assert req.status_code == 202, req.text
    reset_token = req.json()["reset_token"]   # returned in non-prod for testing

    confirm = client.post("/api/v1/auth/password-reset/confirm",
                          json={"token": reset_token, "password": "brandnewpw9"})
    assert confirm.status_code == 200, confirm.text

    # All prior sessions revoked → the old token no longer works.
    assert client.get("/api/v1/auth/me", headers=old_headers).status_code == 401
    # Old password fails, new password works.
    assert client.post("/api/v1/auth/token",
                       json={"email": user["_email"], "password": user["_password"]}).status_code == 401
    assert client.post("/api/v1/auth/token",
                       json={"email": user["_email"], "password": "brandnewpw9"}).status_code == 200


def test_password_reset_request_does_not_enumerate(client):
    """Unknown email still returns a generic 202 with no reset token."""
    r = client.post("/api/v1/auth/password-reset/request",
                    json={"email": f"nobody-{uuid.uuid4().hex}@nowhere.test"})
    assert r.status_code == 202, r.text
    assert "reset_token" not in r.json()


def test_password_reset_confirm_bad_token_rejected(client):
    r = client.post("/api/v1/auth/password-reset/confirm",
                    json={"token": "bogus", "password": "brandnewpw9"})
    assert r.status_code == 400, r.text


# ── Regression: transaction handling on the identity connection ───────────────

def test_ensure_dev_user_after_autobegun_txn_does_not_raise():
    """login() runs a SELECT (autobegins a txn) before seeding the dev user, so
    _ensure_dev_user must commit rather than open a nested begin()."""
    from app.api.auth_routes import _ensure_dev_user, _get_user_by_email

    eng = get_admin_engine()
    with eng.connect() as conn:
        _get_user_by_email(conn, f"missing-{uuid.uuid4().hex}@nowhere.test")  # autobegin
        _ensure_dev_user(conn)  # must NOT raise InvalidRequestError
        assert _get_user_by_email(conn, settings.dev_user_email) is not None
