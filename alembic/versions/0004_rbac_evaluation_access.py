"""Add RBAC columns to evaluation_runs and access_audit_log table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add creator identity columns to evaluation_runs
    op.add_column("evaluation_runs", sa.Column("created_by_email", sa.Text(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("creator_dept_id", sa.Text(), nullable=True))

    # Index for fast department_user filtering in list_runs
    op.create_index("ix_evaluation_runs_created_by_email", "evaluation_runs", ["created_by_email"])

    # Access audit log — who viewed what and when
    op.create_table(
        "access_audit_log",
        sa.Column("log_id", sa.dialects.postgresql.UUID(as_uuid=False),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("org_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("accessed_by", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_access_audit_log_run_id", "access_audit_log", ["run_id"])
    op.create_index("ix_access_audit_log_org_id", "access_audit_log", ["org_id"])

    # Enable RLS on access_audit_log (org isolation)
    op.execute("ALTER TABLE access_audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'access_audit_log'
                  AND policyname = 'rls_access_audit_log'
            ) THEN
                CREATE POLICY rls_access_audit_log ON access_audit_log
                    USING (
                        org_id = CAST(
                            current_setting('app.current_org_id', true) AS uuid
                        )
                    );
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS rls_access_audit_log ON access_audit_log")
    op.drop_index("ix_access_audit_log_org_id", table_name="access_audit_log")
    op.drop_index("ix_access_audit_log_run_id", table_name="access_audit_log")
    op.drop_table("access_audit_log")
    op.drop_index("ix_evaluation_runs_created_by_email", table_name="evaluation_runs")
    op.drop_column("evaluation_runs", "creator_dept_id")
    op.drop_column("evaluation_runs", "created_by_email")
