"""per-minute rate-limit metrics for the cross-process rate monitor

The rate monitor (app/jobs/rate_monitor.py) runs as a separate Modal cron, so it
cannot read the API workers' in-process RateLimiter counters. This table is a
shared, per-minute rolling counter the limiter upserts into (when
RATE_METRICS_ENABLED=true) and the monitor sums over its window. One row per
minute keeps it cheap and naturally bounded.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_stats",
        sa.Column("minute_bucket", sa.TIMESTAMP(timezone=True), primary_key=True),
        sa.Column("total_calls", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rate_limit_errors", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_stats")
