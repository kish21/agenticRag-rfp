"""Phase 7: persist explanation_output for the customer PDF report

Adds a nullable JSONB column to evaluation_runs holding the Explanation agent's
output (vendor narratives + Phase 7 report fields). Previously only
decision_output was persisted; the report needs the narratives too.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("explanation_output", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "explanation_output")
