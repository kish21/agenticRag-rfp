"""tenant isolation: make RLS enforce (P0.16)

Before this migration, Row-Level Security was inert: the app connected as the
table owner/superuser (exempt from RLS), two audit tables had RLS enabled but
no policy, and org_settings used a different GUC name (app.org_id). This:

  1. adds the missing policies on audit_log / access_audit_log,
  2. standardises org_settings(.audit) policies onto app.current_org_id,
  3. FORCEs RLS on every protected table (so it applies even to the owner),
  4. creates a dedicated NON-superuser role `platform_app` (RLS-governed) and
     grants it runtime DML, leaving DDL/identity/cron on the owner role.

Idempotent — mirrors app/db/schema.sql so a schema.sql-bootstrapped DB and a
migrated DB converge. NOTE: dev/CI bootstrap from schema.sql + `alembic stamp
head`, so this body principally runs on real upgrades.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-30
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_PROTECTED_TABLES = [
    "evaluation_setups", "evaluation_runs", "vendor_documents",
    "extracted_certifications", "extracted_insurance", "extracted_slas",
    "extracted_projects", "extracted_pricing", "extracted_facts",
    "decisions", "audit_overrides", "approvals", "audit_log",
    "access_audit_log", "users", "org_criteria_templates",
    "dept_criteria_templates", "org_settings", "org_settings_audit",
    "user_departments", "rfp_collaborators", "approval_assignments",
]


def upgrade() -> None:
    # 1 — policies for the two audit tables that had RLS on but no policy.
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_audit_log') THEN
                CREATE POLICY rls_audit_log ON audit_log
                    USING (org_id::text = current_setting('app.current_org_id', true));
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_access_audit_log') THEN
                CREATE POLICY rls_access_audit_log ON access_audit_log
                    USING (org_id::text = current_setting('app.current_org_id', true));
            END IF;
        END $$;
    """)

    # 2 — standardise org_settings(.audit) onto app.current_org_id.
    op.execute("DROP POLICY IF EXISTS org_settings_isolation ON org_settings;")
    op.execute("""
        CREATE POLICY org_settings_isolation ON org_settings
            USING (org_id = current_setting('app.current_org_id', true));
    """)
    op.execute("DROP POLICY IF EXISTS org_settings_audit_isolation ON org_settings_audit;")
    op.execute("""
        CREATE POLICY org_settings_audit_isolation ON org_settings_audit
            USING (org_id = current_setting('app.current_org_id', true));
    """)

    # 3 — FORCE RLS so the policy applies to the table owner too.
    for t in _PROTECTED_TABLES:
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY;")

    # 4 — dedicated non-superuser application role + runtime grants.
    # DEV/CI bootstrap password; production MUST rotate and set
    # POSTGRES_APP_PASSWORD to match.
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_app') THEN
                CREATE ROLE platform_app LOGIN PASSWORD 'platform_app_pass2026'
                    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            END IF;
        END $$;
    """)
    op.execute("GRANT USAGE ON SCHEMA public TO platform_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO platform_app;")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO platform_app;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO platform_app;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               "GRANT USAGE, SELECT ON SEQUENCES TO platform_app;")


def downgrade() -> None:
    # Un-FORCE RLS (leave it ENABLED) and revert the org_settings GUC name.
    for t in _PROTECTED_TABLES:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS rls_audit_log ON audit_log;")
    op.execute("DROP POLICY IF EXISTS rls_access_audit_log ON access_audit_log;")
    op.execute("DROP POLICY IF EXISTS org_settings_isolation ON org_settings;")
    op.execute("""
        CREATE POLICY org_settings_isolation ON org_settings
            USING (org_id = current_setting('app.org_id', true));
    """)
    op.execute("DROP POLICY IF EXISTS org_settings_audit_isolation ON org_settings_audit;")
    op.execute("""
        CREATE POLICY org_settings_audit_isolation ON org_settings_audit
            USING (org_id = current_setting('app.org_id', true));
    """)
    # Role left in place — dropping it would require reassigning/observing
    # dependent grants; harmless to keep. Revoke runtime DML instead.
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM platform_app;")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM platform_app;")
