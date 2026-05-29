"""Phase 3: llm_response_cache table

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_response_cache",
        sa.Column("cache_key", sa.Text(), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_hit_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("idx_llm_cache_created", "llm_response_cache", ["created_at"])
    op.create_index("idx_llm_cache_model", "llm_response_cache", ["model"])


def downgrade() -> None:
    op.drop_index("idx_llm_cache_model", table_name="llm_response_cache")
    op.drop_index("idx_llm_cache_created", table_name="llm_response_cache")
    op.drop_table("llm_response_cache")
