"""tenant isolation: make RLS enforce (P0.16)

Before this migration RLS was inert: the app connected as the table
owner/superuser (exempt from RLS), two audit tables had RLS enabled but no
policy, and org_settings used a different GUC name (app.org_id). This:

  1. adds missing policies on audit_log / access_audit_log,
  2. standardises org_settings(.audit) onto app.current_org_id,
  3. rewrites simple-org policies to an INDEX-FRIENDLY uuid predicate
     (`org_id = NULLIF(current_setting(...), '')::uuid`) so the org filter can
     use the `(org_id, …)` indexes instead of a text-cast seq scan,
  4. brings the operational tenant tables (rfps, ingestion_jobs, event_log,
     invited_vendors) under RLS,
  5. FORCEs RLS on every RLS-enabled table (applies even to the owner),
  6. creates a dedicated NON-superuser role `platform_app` whose password is
     read from the POSTGRES_APP_PASSWORD env var — no credential in source,
  7. adds the evaluation_runs.gaps_report column the run-results route needs.

Idempotent; mirrors app/db/schema.sql. Dev/CI bootstrap from schema.sql +
`alembic stamp head`, so this body principally runs on real upgrades.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-30
"""
import os

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# (table, policy_name) for the simple single-column uuid org_id policies.
_UUID_ORG_POLICIES = [
    ("evaluation_setups", "rls_evaluation_setups"),
    ("evaluation_runs", "rls_evaluation_runs"),
    ("vendor_documents", "rls_vendor_docs"),
    ("extracted_certifications", "rls_certifications"),
    ("extracted_insurance", "rls_insurance"),
    ("extracted_slas", "rls_slas"),
    ("extracted_projects", "rls_projects"),
    ("extracted_pricing", "rls_pricing"),
    ("extracted_facts", "rls_extracted_facts"),
    ("decisions", "rls_decisions"),
    ("audit_overrides", "rls_audit_overrides"),
    ("approvals", "rls_approvals"),
    ("users", "users_org_isolation"),
    ("org_criteria_templates", "org_criteria_isolation"),
    ("dept_criteria_templates", "dept_criteria_isolation"),
    ("audit_log", "rls_audit_log"),
    ("access_audit_log", "rls_access_audit_log"),
]

_UUID_PRED = "org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def _app_password() -> str:
    pw = os.environ.get("POSTGRES_APP_PASSWORD")
    if not pw:
        raise RuntimeError(
            "POSTGRES_APP_PASSWORD must be set to provision the platform_app role "
            "(no credential is hardcoded). Set it in the environment / secrets manager."
        )
    return pw


def upgrade() -> None:
    # 1 — index-friendly uuid policies (DROP + CREATE; covers fresh & existing).
    for table, policy in _UUID_ORG_POLICIES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
        op.execute(f"CREATE POLICY {policy} ON {table} USING ({_UUID_PRED});")

    # Legacy index-unfriendly duplicate on audit_log (pre-dates rls_audit_log).
    op.execute("DROP POLICY IF EXISTS audit_log_org_isolation ON audit_log;")

    # 2 — org_settings(.audit): text org_id, standardise GUC name.
    op.execute("DROP POLICY IF EXISTS org_settings_isolation ON org_settings;")
    op.execute("CREATE POLICY org_settings_isolation ON org_settings "
               "USING (org_id = current_setting('app.current_org_id', true));")
    op.execute("DROP POLICY IF EXISTS org_settings_audit_isolation ON org_settings_audit;")
    op.execute("CREATE POLICY org_settings_audit_isolation ON org_settings_audit "
               "USING (org_id = current_setting('app.current_org_id', true));")

    # 3 — operational tenant tables.
    for table, policy in (("rfps", "rls_rfps"), ("ingestion_jobs", "rls_ingestion_jobs"),
                          ("event_log", "rls_event_log")):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
        op.execute(f"CREATE POLICY {policy} ON {table} USING ({_UUID_PRED});")
    op.execute("ALTER TABLE invited_vendors ENABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS rls_invited_vendors ON invited_vendors;")
    op.execute(
        "CREATE POLICY rls_invited_vendors ON invited_vendors USING ("
        "EXISTS (SELECT 1 FROM rfps r WHERE r.rfp_id = invited_vendors.rfp_id "
        f"AND r.{_UUID_PRED}));"
    )

    # 4 — FORCE RLS on every RLS-enabled table (single source of truth).
    op.execute("""
        DO $$ DECLARE t regclass;
        BEGIN
            FOR t IN SELECT oid FROM pg_class
                     WHERE relrowsecurity = true AND relnamespace = 'public'::regnamespace
            LOOP EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', t); END LOOP;
        END $$;
    """)

    # 5 — dedicated non-superuser role; password from env (no literal in source).
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_app') THEN
                CREATE ROLE platform_app LOGIN
                    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            END IF;
        END $$;
    """)
    op.execute(f"ALTER ROLE platform_app PASSWORD '{_app_password()}';")
    op.execute("GRANT USAGE ON SCHEMA public TO platform_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO platform_app;")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO platform_app;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO platform_app;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               "GRANT USAGE, SELECT ON SEQUENCES TO platform_app;")

    # 6 — column the run-results / override routes read & write.
    op.execute("ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS gaps_report JSONB;")


def downgrade() -> None:
    for table in ("rfps", "ingestion_jobs", "event_log", "invited_vendors"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
    for table, _ in _UUID_ORG_POLICIES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM platform_app;")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM platform_app;")
    # Policies/role/column left in place — harmless and avoids reintroducing the
    # inert state. Re-running upgrade() is idempotent.
