"""Phase 5 foundation: rfps, invited_vendors, ingestion_jobs, event_log

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rfps",
        sa.Column("rfp_id", sa.Text(), primary_key=True),
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("department", sa.Text()),
        sa.Column("created_by_email", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("submission_deadline", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "submission_status",
            sa.Text(),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "autonomy_mode",
            sa.Text(),
            nullable=False,
            server_default="auto_to_evaluate",
        ),
        sa.CheckConstraint(
            "submission_status IN ('open','closed','processing','facts_ready','evaluated')",
            name="rfps_submission_status_check",
        ),
        sa.CheckConstraint(
            "autonomy_mode IN ('manual','auto_to_evaluate','auto_to_report')",
            name="rfps_autonomy_mode_check",
        ),
    )
    op.create_index("ix_rfps_org", "rfps", ["org_id"])
    op.create_index(
        "ix_rfps_deadline_open",
        "rfps",
        ["submission_deadline"],
        postgresql_where=sa.text("submission_status = 'open'"),
    )

    op.create_table(
        "invited_vendors",
        sa.Column("rfp_id", sa.Text(), nullable=False),
        sa.Column("vendor_id", sa.Text(), nullable=False),
        sa.Column("vendor_name", sa.Text()),
        sa.Column("invited_by", sa.Text(), nullable=False),
        sa.Column("invited_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("rfp_id", "vendor_id"),
        sa.ForeignKeyConstraint(["rfp_id"], ["rfps.rfp_id"], ondelete="CASCADE"),
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("rfp_id", sa.Text(), nullable=False),
        sa.Column("vendor_id", sa.Text(), nullable=False),
        sa.Column("source_uri", sa.Text()),
        sa.Column("filename", sa.Text()),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attribution_confidence", sa.Float()),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("attempted_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("error", sa.Text()),
        sa.Column("doc_id", sa.dialects.postgresql.UUID(as_uuid=False)),
        sa.Column("superseded_by", sa.dialects.postgresql.UUID(as_uuid=False)),
        sa.ForeignKeyConstraint(["doc_id"], ["vendor_documents.doc_id"]),
        sa.ForeignKeyConstraint(["superseded_by"], ["ingestion_jobs.job_id"]),
        sa.UniqueConstraint("rfp_id", "vendor_id", "content_hash", name="uq_ingestion_jobs_rfp_vendor_hash"),
        sa.CheckConstraint(
            "status IN ('received','superseded','queued','processing','facts_ready',"
            "'failed','duplicate','needs_attribution','rejected_late')",
            name="ingestion_jobs_status_check",
        ),
    )
    op.create_index("ix_ingestion_jobs_rfp_status", "ingestion_jobs", ["rfp_id", "status"])

    op.create_table(
        "event_log",
        sa.Column("event_id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("rfp_id", sa.Text(), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index(
        "ix_event_log_pending",
        "event_log",
        ["created_at"],
        postgresql_where=sa.text("delivered_at IS NULL"),
    )
    op.create_index("ix_event_log_rfp", "event_log", ["rfp_id"])


def downgrade() -> None:
    op.drop_index("ix_event_log_rfp", table_name="event_log")
    op.drop_index("ix_event_log_pending", table_name="event_log")
    op.drop_table("event_log")

    op.drop_index("ix_ingestion_jobs_rfp_status", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")

    op.drop_table("invited_vendors")

    op.drop_index("ix_rfps_deadline_open", table_name="rfps")
    op.drop_index("ix_rfps_org", table_name="rfps")
    op.drop_table("rfps")
