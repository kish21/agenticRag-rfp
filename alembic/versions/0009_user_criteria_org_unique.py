"""scope user_criteria uniqueness to (email, org_id) for tenant isolation

The original table (0003) put a column-level UNIQUE on `email` alone. Because the
platform allows the same email across organisations, that constraint let one org's
criteria collide with another's: `ON CONFLICT (email)` in the save path would
overwrite (and the read path could surface) a same-email user's row in a different
org. Move uniqueness to (email, org_id) so each org has its own row.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-30
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres auto-names a column-level UNIQUE as <table>_<column>_key.
    op.drop_constraint("user_criteria_email_key", "user_criteria", type_="unique")
    op.create_unique_constraint(
        "uq_user_criteria_email_org", "user_criteria", ["email", "org_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_criteria_email_org", "user_criteria", type_="unique")
    op.create_unique_constraint("user_criteria_email_key", "user_criteria", ["email"])
