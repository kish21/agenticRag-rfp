"""human feedback capture → few-shot bank: evaluation_corrections (#60 / P1.9)

P1.9 turns human corrections of AI evaluations into an org-scoped few-shot
example bank that guides the Evaluation Agent. The existing audit_overrides
table records WHOLE-VENDOR overrides only; this table captures the finer
criterion/check-level corrections the few-shot bank selects on (org_id +
target). Every correction ALSO writes an AuditOverride for the audit trail
(Component Contract #7) — this table is the learning signal, not the audit of
record.

Org-isolated by RLS on org_id (same index-friendly uuid predicate as every
other tenant table) and FORCEd so even the table owner is constrained. A tenant
only ever learns from its OWN corrections.

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_PRED = "org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "evaluation_corrections",
        sa.Column("correction_id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False)),
        sa.Column("vendor_id", sa.Text()),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("target_name", sa.Text()),
        sa.Column("original_value", postgresql.JSONB()),
        sa.Column("corrected_value", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("corrected_by", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("target_type IN ('criterion','check')",
                           name="evaluation_corrections_target_type_check"),
        sa.CheckConstraint("length(reason) >= 20",
                           name="evaluation_corrections_reason_check"),
    )
    op.create_index(
        "idx_eval_corrections_lookup",
        "evaluation_corrections",
        ["org_id", "target_type", "target_id", "active"],
    )

    # Tenant isolation — same pattern as every other org-scoped table.
    op.execute("ALTER TABLE evaluation_corrections ENABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS rls_evaluation_corrections ON evaluation_corrections;")
    op.execute(f"CREATE POLICY rls_evaluation_corrections ON evaluation_corrections USING ({_PRED});")
    op.execute("ALTER TABLE evaluation_corrections FORCE ROW LEVEL SECURITY;")

    # The application role needs DML on the new table. ALTER DEFAULT PRIVILEGES
    # (set in 0011) should cover this, but grant explicitly so the table is
    # usable regardless of which role ran the migration.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON evaluation_corrections TO platform_app;")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS rls_evaluation_corrections ON evaluation_corrections;")
    op.drop_index("idx_eval_corrections_lookup", table_name="evaluation_corrections")
    op.drop_table("evaluation_corrections")
