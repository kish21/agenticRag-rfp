"""
tests/test_jwt_pyjwt_migration.py
=================================
Guards the python-jose → PyJWT migration (#222). These are pure, infra-free
unit tests (no DB) — they exercise the JWT mint/verify contract directly.

Proves:
  • a minted token round-trips back to the same TokenData
  • EVERY failure mode (garbage / tampered / expired / missing fields / bad
    role) surfaces as the app-level TokenError — NOT a leaked library exception,
    so callers (dependencies, middleware) only ever catch TokenError
  • no app module re-imports `jose` (regression guard: the whole point of #222
    is to be off python-jose, which also clears the two CVE ignores)

Run:
    python -m pytest tests/test_jwt_pyjwt_migration.py -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from app.auth.jwt import (
    TokenError,
    create_access_token,
    decode_token,
)
from app.config import settings


def _mint(**overrides) -> str:
    """Mint a raw JWT directly via PyJWT so a test can backdate exp / drop
    fields the public create_access_token would never emit."""
    payload = {
        "sub": "user@example.com",
        "org_id": "org-1",
        "role": "company_admin",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    payload.update(overrides)
    return pyjwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def test_round_trip_preserves_claims():
    tok = create_access_token(
        email="user@example.com",
        org_id="org-1",
        role="company_admin",
        dept_id="dept-9",
    )
    td = decode_token(tok.access_token)
    assert td.email == "user@example.com"
    assert td.org_id == "org-1"
    assert td.role == "company_admin"
    assert td.dept_id == "dept-9"
    assert td.jti == tok.jti  # jti embedded in the signed token == returned jti


def test_garbage_token_raises_token_error():
    with pytest.raises(TokenError):
        decode_token("not.a.jwt")


def test_tampered_signature_raises_token_error():
    tok = create_access_token(
        email="user@example.com", org_id="org-1", role="company_admin"
    )
    with pytest.raises(TokenError):
        decode_token(tok.access_token + "tampered")


def test_expired_token_raises_token_error():
    expired = _mint(exp=datetime.now(timezone.utc) - timedelta(hours=1))
    with pytest.raises(TokenError):
        decode_token(expired)


def test_missing_required_field_raises_token_error():
    # A validly-signed token that omits org_id must still be rejected.
    no_org = _mint(org_id=None)
    with pytest.raises(TokenError):
        decode_token(no_org)


def test_invalid_role_raises_token_error():
    bad_role = _mint(role="superuser")
    with pytest.raises(TokenError):
        decode_token(bad_role)


def test_wrong_secret_raises_token_error():
    forged = pyjwt.encode(
        {
            "sub": "user@example.com",
            "org_id": "org-1",
            "role": "company_admin",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        "the-wrong-secret-key",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(TokenError):
        decode_token(forged)


def test_no_app_module_imports_jose():
    """Regression guard: #222 left python-jose behind for good. If any auth
    module imports `jose` again the CVE ignores we removed would silently
    return."""
    import importlib

    for mod_name in (
        "app.auth.jwt",
        "app.auth.dependencies",
        "app.api.middleware",
    ):
        mod = importlib.import_module(mod_name)
        src = (
            (mod.__file__ or "")
            and open(mod.__file__, encoding="utf-8").read()
        )
        assert "jose" not in src, f"{mod_name} still references python-jose"
