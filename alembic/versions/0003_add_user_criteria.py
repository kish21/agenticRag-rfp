"""add user_criteria table for personal success criteria storage

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_criteria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("org_id", sa.Text(), nullable=False),
        sa.Column("criteria", JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_user_criteria_email", "user_criteria", ["email"])


def downgrade() -> None:
    op.drop_index("ix_user_criteria_email", table_name="user_criteria")
    op.drop_table("user_criteria")
