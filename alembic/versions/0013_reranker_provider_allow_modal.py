"""allow 'modal' in the org_settings.reranker_provider CHECK constraint

The reranker provider abstraction (app/providers/reranker.py) and .env's
RERANKER_PROVIDER support `modal` (the BGE CrossEncoder run on a Modal A10G —
identical model to `bge`, no local HuggingFace egress). The org_settings CHECK
constraint predates that provider and only allowed ('cohere','bge','colbert',
'none'), so a per-org setting of `modal` was rejected at the DB. This widens the
constraint to include `modal`. No data change — purely a constraint relaxation.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-02
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_CONSTRAINT = "org_settings_reranker_provider_check"
_OLD = "('cohere','bge','colbert','none')"
_NEW = "('cohere','bge','colbert','modal','none')"


def upgrade() -> None:
    op.execute(f"ALTER TABLE org_settings DROP CONSTRAINT IF EXISTS {_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE org_settings ADD CONSTRAINT {_CONSTRAINT} "
        f"CHECK (reranker_provider IN {_NEW})"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE org_settings DROP CONSTRAINT IF EXISTS {_CONSTRAINT}")
    op.execute(
        f"ALTER TABLE org_settings ADD CONSTRAINT {_CONSTRAINT} "
        f"CHECK (reranker_provider IN {_OLD})"
    )
