"""add llm cost and token columns to evaluation_runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("llm_cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("llm_tokens_total", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "llm_tokens_total")
    op.drop_column("evaluation_runs", "llm_cost_usd")
