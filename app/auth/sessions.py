"""
Server-side session allowlist for JWT revocation (E2 auth hardening).

A signed JWT cannot be invalidated before its ``exp`` by itself — that is the
core limitation this module fixes. Every issued token carries a unique ``jti``;
at issue time we record a row in ``auth_sessions``. ``get_current_user`` then
checks the session is still active on each request, so a token can be revoked
server-side on logout, on a forced sign-out (departure / breach), or on a
password reset.

All access goes through the OWNER (admin) engine: this is part of the identity
path, which runs before / outside any tenant org-context. The table is still
RLS-protected (defence in depth) — the owner is a superuser and bypasses RLS.
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa


def issue_session(
    conn,
    *,
    jti: str,
    user_id: str,
    org_id: str,
    expires_at: datetime,
) -> None:
    """Record a freshly minted token's jti in the allowlist."""
    conn.execute(
        sa.text(
            """
            INSERT INTO auth_sessions (jti, user_id, org_id, expires_at)
            VALUES (CAST(:jti AS uuid), CAST(:user_id AS uuid),
                    CAST(:org_id AS uuid), :expires_at)
            ON CONFLICT (jti) DO NOTHING
            """
        ),
        {"jti": jti, "user_id": user_id, "org_id": org_id, "expires_at": expires_at},
    )


def session_is_active(conn, jti: str) -> bool:
    """True iff a session row exists for ``jti`` and is neither revoked nor expired."""
    if not jti:
        return False
    row = conn.execute(
        sa.text(
            """
            SELECT 1 FROM auth_sessions
            WHERE jti = CAST(:jti AS uuid)
              AND revoked_at IS NULL
              AND expires_at > now()
            """
        ),
        {"jti": jti},
    ).fetchone()
    return row is not None


def revoke_session(conn, jti: str, reason: str = "logout") -> None:
    """Revoke a single session (e.g. logout of this device)."""
    conn.execute(
        sa.text(
            """
            UPDATE auth_sessions
               SET revoked_at = now(), revoked_reason = :reason
             WHERE jti = CAST(:jti AS uuid) AND revoked_at IS NULL
            """
        ),
        {"jti": jti, "reason": reason},
    )


def revoke_user_sessions(conn, user_id: str, reason: str = "revoked") -> int:
    """Revoke ALL active sessions for a user (departure / breach / password reset).

    Returns the number of sessions revoked."""
    result = conn.execute(
        sa.text(
            """
            UPDATE auth_sessions
               SET revoked_at = now(), revoked_reason = :reason
             WHERE user_id = CAST(:user_id AS uuid) AND revoked_at IS NULL
            """
        ),
        {"user_id": user_id, "reason": reason},
    )
    return result.rowcount or 0


def purge_expired_sessions(conn) -> int:
    """Delete sessions whose tokens have already expired (housekeeping)."""
    result = conn.execute(
        sa.text("DELETE FROM auth_sessions WHERE expires_at < now()")
    )
    return result.rowcount or 0
