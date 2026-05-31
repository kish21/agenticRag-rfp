"""
One-time, expiring tokens for invite-acceptance and password-reset
(E2 auth hardening).

Why this exists:
  • Invites must not return a plaintext/temporary password. Instead the admin
    receives a single-use invite token (a link) that the invitee redeems to set
    their own password.
  • Password reset needs an out-of-band, expiring, single-use secret.

Security properties:
  • Only a SHA-256 hash of the token is stored — the plaintext exists only in
    the link handed to the user, never at rest.
  • Tokens are high-entropy (``secrets.token_urlsafe(32)``), so a fast hash is
    appropriate here (unlike user passwords, which use bcrypt).
  • Single-use: ``consume_token`` atomically stamps ``used_at`` and refuses an
    already-used or expired token.

Accessed via the OWNER (admin) engine — part of the identity path. RLS-protected
for defence in depth.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlalchemy as sa

INVITE = "invite"
PASSWORD_RESET = "password_reset"
_PURPOSES = {INVITE, PASSWORD_RESET}

# Default lifetimes. Invites are longer-lived (a colleague may take days to
# accept); reset links are deliberately short.
INVITE_TTL_HOURS = 72
RESET_TTL_HOURS = 1


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def create_onetime_token(
    conn,
    *,
    purpose: str,
    email: str,
    org_id: Optional[str] = None,
    role: Optional[str] = None,
    dept_id: Optional[str] = None,
    user_id: Optional[str] = None,
    ttl_hours: Optional[int] = None,
) -> str:
    """Create a single-use token and return its PLAINTEXT (caller delivers it).

    Only the hash is persisted. Any prior unused token for the same
    (purpose, email) is invalidated so a user never holds two live links.
    """
    if purpose not in _PURPOSES:
        raise ValueError(f"Unknown token purpose: {purpose}")

    if ttl_hours is None:
        ttl_hours = INVITE_TTL_HOURS if purpose == INVITE else RESET_TTL_HOURS

    plaintext = secrets.token_urlsafe(32)
    token_hash = _hash(plaintext)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    # Supersede any earlier live token of the same purpose for this email.
    conn.execute(
        sa.text(
            """
            UPDATE auth_onetime_tokens
               SET used_at = now()
             WHERE purpose = :purpose AND email = :email AND used_at IS NULL
            """
        ),
        {"purpose": purpose, "email": email},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO auth_onetime_tokens
                (token_hash, purpose, email, org_id, role, dept_id, user_id, expires_at)
            VALUES (
                :token_hash, :purpose, :email,
                CAST(NULLIF(:org_id, '') AS uuid), :role,
                CAST(NULLIF(:dept_id, '') AS uuid),
                CAST(NULLIF(:user_id, '') AS uuid), :expires_at
            )
            """
        ),
        {
            "token_hash": token_hash,
            "purpose": purpose,
            "email": email,
            "org_id": org_id or "",
            "role": role,
            "dept_id": dept_id or "",
            "user_id": user_id or "",
            "expires_at": expires_at,
        },
    )
    return plaintext


def consume_token(conn, plaintext: str, purpose: str) -> Optional[dict]:
    """Validate and atomically spend a one-time token.

    Returns the token's payload (email/org_id/role/dept_id/user_id) on success,
    or None if the token is unknown, the wrong purpose, expired, or already used.
    The UPDATE...RETURNING is atomic, so a token cannot be redeemed twice even
    under a race.
    """
    if not plaintext:
        return None
    token_hash = _hash(plaintext)
    row = conn.execute(
        sa.text(
            """
            UPDATE auth_onetime_tokens
               SET used_at = now()
             WHERE token_hash = :token_hash
               AND purpose = :purpose
               AND used_at IS NULL
               AND expires_at > now()
            RETURNING email, org_id::text, role, dept_id::text, user_id::text
            """
        ),
        {"token_hash": token_hash, "purpose": purpose},
    ).fetchone()
    if row is None:
        return None
    return dict(zip(["email", "org_id", "role", "dept_id", "user_id"], row))
