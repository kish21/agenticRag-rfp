"""add 'auditor' to the users.role CHECK constraint (#55)

#55 introduces a read-only compliance persona, `auditor`, that can review the
org's audit trail (access_audit_log + audit_log) but cannot run/override
evaluations or see evaluation content. The JWT layer already validates the role
string; this migration widens the database CHECK so an auditor user row persists.

No data change — only the allowed-value set on users.role expands. Existing rows
keep their value. Downgrade refuses if any auditor rows exist (dropping the value
while rows reference it would leave the table un-recreatable on a re-upgrade).

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-06
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_ROLES_WITH_AUDITOR = "'platform_admin','company_admin','department_admin','department_user','auditor'"
_ROLES_WITHOUT = "'platform_admin','company_admin','department_admin','department_user'"


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute(
        f"ALTER TABLE users ADD CONSTRAINT users_role_check "
        f"CHECK (role IN ({_ROLES_WITH_AUDITOR}))"
    )


def downgrade() -> None:
    # Fail loudly rather than silently violate the narrower constraint.
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM users WHERE role = 'auditor') THEN "
        "RAISE EXCEPTION 'Cannot downgrade: auditor users exist; reassign them first'; "
        "END IF; END $$;"
    )
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute(
        f"ALTER TABLE users ADD CONSTRAINT users_role_check "
        f"CHECK (role IN ({_ROLES_WITHOUT}))"
    )
