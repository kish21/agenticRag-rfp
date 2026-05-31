"""auth hardening: session allowlist + one-time tokens (E2)

Adds the two tables that give the auth system server-side revocation and
password-less invite / reset flows:

  1. auth_sessions       — one row per issued JWT (jti). get_current_user checks
                           it on every request, so a token can be revoked before
                           expiry (logout / forced sign-out / password reset).
  2. auth_onetime_tokens — single-use, expiring, hash-at-rest tokens for invite
                           acceptance and password reset (no plaintext password
                           ever leaves the server).

Both are RLS-enabled + FORCEd + granted to platform_app, mirroring 0011 and
app/db/schema.sql. Idempotent; dev/CI bootstrap from schema.sql then
`alembic stamp head`, so this body principally runs on real upgrades.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-31
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_UUID_PRED = "org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            jti            UUID PRIMARY KEY,
            user_id        UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            org_id         UUID NOT NULL REFERENCES organisations(org_id) ON DELETE CASCADE,
            issued_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at     TIMESTAMPTZ NOT NULL,
            revoked_at     TIMESTAMPTZ,
            revoked_reason TEXT
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_active "
        "ON auth_sessions(jti) WHERE revoked_at IS NULL;"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_onetime_tokens (
            token_hash  TEXT PRIMARY KEY,
            purpose     TEXT NOT NULL CHECK (purpose IN ('invite', 'password_reset')),
            email       TEXT NOT NULL,
            org_id      UUID REFERENCES organisations(org_id) ON DELETE CASCADE,
            role        TEXT,
            dept_id     UUID,
            user_id     UUID REFERENCES users(user_id) ON DELETE CASCADE,
            expires_at  TIMESTAMPTZ NOT NULL,
            used_at     TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_onetime_email "
        "ON auth_onetime_tokens(purpose, email) WHERE used_at IS NULL;"
    )

    # RLS (defence in depth; the identity path uses the RLS-exempt owner role).
    op.execute("ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS rls_auth_sessions ON auth_sessions;")
    op.execute(f"CREATE POLICY rls_auth_sessions ON auth_sessions USING ({_UUID_PRED});")
    op.execute("ALTER TABLE auth_sessions FORCE ROW LEVEL SECURITY;")

    op.execute("ALTER TABLE auth_onetime_tokens ENABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS rls_auth_onetime_tokens ON auth_onetime_tokens;")
    op.execute(
        "CREATE POLICY rls_auth_onetime_tokens ON auth_onetime_tokens "
        f"USING (org_id IS NULL OR {_UUID_PRED});"
    )
    op.execute("ALTER TABLE auth_onetime_tokens FORCE ROW LEVEL SECURITY;")

    # Explicit grants (belt-and-braces alongside 0011's ALTER DEFAULT PRIVILEGES).
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON auth_sessions, auth_onetime_tokens "
        "TO platform_app;"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_onetime_tokens;")
    op.execute("DROP TABLE IF EXISTS auth_sessions;")
