"""align the stale org_settings.reranker_provider column DEFAULT (cohere -> bge)

The column DEFAULT was 'cohere', a stale pre-ADR-004 value. It is never hit by
application code (upsert_org_settings always writes the column explicitly), but a
manual INSERT omitting the column would silently default to the paid Cohere API —
which fails with no key configured. ADR-004 makes BGE the documented product
default, and loader.py's .env fallback default is 'bge', so this aligns the last
stale surface. No data change — existing rows keep their value; only the column
DEFAULT for future column-omitted inserts changes.

Note: the resolved default for a brand-new org (no org_settings row) is sourced
from .env RERANKER_PROVIDER in domain/org_settings._defaults_for (issue #212) —
the DB DEFAULT is purely a last-resort safety net for a direct INSERT.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-04
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE org_settings ALTER COLUMN reranker_provider SET DEFAULT 'bge'")


def downgrade() -> None:
    op.execute("ALTER TABLE org_settings ALTER COLUMN reranker_provider SET DEFAULT 'cohere'")
