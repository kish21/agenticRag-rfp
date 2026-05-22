"""Add currency column to evaluation_runs

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column("currency", sa.Text(), nullable=False, server_default="GBP"),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "currency")
