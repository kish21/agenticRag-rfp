"""initial schema — baseline from schema.sql

Revision ID: 0001
Revises:
Create Date: 2026-05-18

This migration captures the complete schema as it exists in schema.sql.
All tables are created with IF NOT EXISTS so this is safe to run against
a database that was previously bootstrapped with the raw schema.sql file.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS organisations (
            org_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_name          TEXT NOT NULL,
            industry          TEXT,
            subscription_tier TEXT DEFAULT 'starter',
            created_at        TIMESTAMPTZ DEFAULT now(),
            is_active         BOOLEAN DEFAULT true
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_registry (
            agent_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id       UUID REFERENCES organisations(org_id),
            agent_name   TEXT NOT NULL,
            agent_type   TEXT NOT NULL,
            department   TEXT,
            config       JSONB NOT NULL,
            is_active    BOOLEAN DEFAULT true,
            created_at   TIMESTAMPTZ DEFAULT now(),
            updated_at   TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_setups (
            setup_id       TEXT PRIMARY KEY,
            org_id         UUID NOT NULL,
            department     TEXT NOT NULL,
            rfp_id         TEXT NOT NULL,
            setup_json     JSONB NOT NULL,
            confirmed_by   TEXT NOT NULL,
            confirmed_at   TIMESTAMPTZ,
            source         TEXT NOT NULL,
            created_at     TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_runs (
            run_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id           UUID NOT NULL,
            setup_id         TEXT REFERENCES evaluation_setups(setup_id),
            rfp_id           TEXT NOT NULL,
            rfp_title        TEXT,
            department       TEXT,
            rfp_filename     TEXT,
            rfp_bytes        BYTEA,
            agent_id         UUID REFERENCES agent_registry(agent_id),
            status           TEXT DEFAULT 'running',
            vendor_ids       TEXT[],
            contract_value   NUMERIC,
            approval_tier    INTEGER,
            langsmith_trace  TEXT,
            agent_events     JSONB NOT NULL DEFAULT '[]',
            agent_log        JSONB NOT NULL DEFAULT '[]',
            decision_output  JSONB,
            vendor_names     JSONB DEFAULT '{}',
            created_at       TIMESTAMPTZ DEFAULT now(),
            completed_at     TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS vendor_documents (
            doc_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        UUID NOT NULL,
            vendor_id     TEXT NOT NULL,
            rfp_id        TEXT NOT NULL,
            setup_id      TEXT REFERENCES evaluation_setups(setup_id),
            filename      TEXT NOT NULL,
            file_name     TEXT,
            file_bytes    BYTEA,
            content_hash  TEXT NOT NULL,
            quality_score FLOAT,
            total_chunks  INTEGER,
            ingested_at   TIMESTAMPTZ DEFAULT now(),
            UNIQUE(org_id, vendor_id, rfp_id, content_hash)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS extracted_certifications (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            doc_id          UUID REFERENCES vendor_documents(doc_id),
            org_id          UUID NOT NULL,
            vendor_id       TEXT NOT NULL,
            standard_name   TEXT,
            version         TEXT,
            cert_number     TEXT,
            issuing_body    TEXT,
            scope           TEXT,
            valid_until     DATE,
            status          TEXT,
            confidence      FLOAT,
            grounding_quote TEXT NOT NULL,
            source_chunk_id TEXT NOT NULL,
            created_at      TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS extracted_insurance (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            doc_id          UUID REFERENCES vendor_documents(doc_id),
            org_id          UUID NOT NULL,
            vendor_id       TEXT NOT NULL,
            insurance_type  TEXT,
            amount_gbp      NUMERIC,
            currency        TEXT DEFAULT 'GBP',
            provider        TEXT,
            confidence      FLOAT,
            grounding_quote TEXT NOT NULL,
            source_chunk_id TEXT NOT NULL,
            created_at      TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS extracted_slas (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            doc_id            UUID REFERENCES vendor_documents(doc_id),
            org_id            UUID NOT NULL,
            vendor_id         TEXT NOT NULL,
            priority_level    TEXT,
            response_minutes  INTEGER,
            resolution_hours  INTEGER,
            uptime_percentage FLOAT,
            confidence        FLOAT,
            grounding_quote   TEXT NOT NULL,
            source_chunk_id   TEXT NOT NULL,
            created_at        TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS extracted_projects (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            doc_id              UUID REFERENCES vendor_documents(doc_id),
            org_id              UUID NOT NULL,
            vendor_id           TEXT NOT NULL,
            client_name         TEXT,
            client_sector       TEXT,
            user_count          INTEGER,
            outcomes            TEXT,
            reference_available BOOLEAN,
            confidence          FLOAT,
            grounding_quote     TEXT NOT NULL,
            source_chunk_id     TEXT NOT NULL,
            created_at          TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS extracted_pricing (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            doc_id          UUID REFERENCES vendor_documents(doc_id),
            org_id          UUID NOT NULL,
            vendor_id       TEXT NOT NULL,
            year            INTEGER,
            amount_gbp      NUMERIC,
            total_gbp       NUMERIC,
            currency        TEXT DEFAULT 'GBP',
            includes        TEXT[],
            confidence      FLOAT,
            grounding_quote TEXT NOT NULL,
            source_chunk_id TEXT NOT NULL,
            created_at      TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS extracted_facts (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            doc_id          UUID REFERENCES vendor_documents(doc_id),
            org_id          UUID NOT NULL,
            vendor_id       TEXT NOT NULL,
            setup_id        TEXT REFERENCES evaluation_setups(setup_id),
            target_id       TEXT NOT NULL,
            fact_type       TEXT NOT NULL,
            fact_name       TEXT NOT NULL,
            text_value      TEXT,
            numeric_value   NUMERIC,
            boolean_value   BOOLEAN,
            unit            TEXT,
            confidence      FLOAT,
            grounding_quote TEXT NOT NULL,
            source_chunk_id TEXT NOT NULL,
            created_at      TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            decision_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id          UUID REFERENCES evaluation_runs(run_id),
            org_id          UUID NOT NULL,
            vendor_id       TEXT,
            decision_type   TEXT,
            check_id        TEXT,
            criterion_id    TEXT,
            decision        TEXT,
            score_value     NUMERIC,
            confidence      FLOAT,
            reasoning       TEXT,
            evidence_quote  TEXT,
            source_doc      TEXT,
            created_at      TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_overrides (
            override_id       UUID PRIMARY KEY,
            org_id            UUID NOT NULL,
            run_id            UUID,
            overridden_by     TEXT NOT NULL,
            original_decision JSONB NOT NULL,
            new_decision      JSONB NOT NULL,
            reason            TEXT NOT NULL CHECK (length(reason) >= 20),
            timestamp         TIMESTAMPTZ NOT NULL,
            approved_by       TEXT
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id         UUID REFERENCES evaluation_runs(run_id),
            org_id         UUID NOT NULL,
            approval_tier  INTEGER NOT NULL,
            approver_role  TEXT NOT NULL,
            status         TEXT DEFAULT 'pending',
            comments       TEXT,
            requested_at   TIMESTAMPTZ DEFAULT now(),
            responded_at   TIMESTAMPTZ,
            sla_deadline   TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            log_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id      UUID NOT NULL,
            run_id      UUID REFERENCES evaluation_runs(run_id) ON DELETE SET NULL,
            event_type  TEXT NOT NULL,
            actor       TEXT NOT NULL DEFAULT 'system',
            agent       TEXT,
            detail      JSONB,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id     UUID NOT NULL REFERENCES organisations(org_id) ON DELETE CASCADE,
            email      TEXT NOT NULL,
            hashed_pw  TEXT NOT NULL,
            role       TEXT NOT NULL DEFAULT 'department_user'
                           CHECK (role IN ('platform_admin','company_admin','department_admin','department_user')),
            dept_id    UUID,
            is_active  BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (email)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS tenant_modules (
            org_id       UUID NOT NULL REFERENCES organisations(org_id) ON DELETE CASCADE,
            module_key   TEXT NOT NULL,
            enabled      BOOLEAN NOT NULL DEFAULT FALSE,
            config       JSONB NOT NULL DEFAULT '{}',
            activated_at TIMESTAMPTZ,
            PRIMARY KEY (org_id, module_key)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS tenant_billing (
            org_id                 UUID PRIMARY KEY REFERENCES organisations(org_id) ON DELETE CASCADE,
            stripe_customer_id     TEXT,
            stripe_subscription_id TEXT,
            plan                   TEXT NOT NULL DEFAULT 'trial'
                                       CHECK (plan IN ('trial','starter','professional','enterprise')),
            modules_active         TEXT[] NOT NULL DEFAULT '{}',
            next_billing           TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS org_criteria_templates (
            template_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id         UUID NOT NULL REFERENCES organisations(org_id) ON DELETE CASCADE,
            check_type     TEXT NOT NULL CHECK (check_type IN ('mandatory','scoring')),
            name           TEXT NOT NULL,
            description    TEXT DEFAULT '',
            what_passes    TEXT DEFAULT '',
            default_weight DECIMAL(4,3) DEFAULT 0.0,
            rubric         JSONB DEFAULT '{}',
            applies_to     TEXT DEFAULT 'all',
            is_locked      BOOLEAN DEFAULT FALSE,
            created_by     TEXT DEFAULT 'system',
            created_at     TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS dept_criteria_templates (
            template_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id         UUID NOT NULL REFERENCES organisations(org_id) ON DELETE CASCADE,
            department     TEXT NOT NULL,
            check_type     TEXT NOT NULL CHECK (check_type IN ('mandatory','scoring')),
            name           TEXT NOT NULL,
            description    TEXT DEFAULT '',
            what_passes    TEXT DEFAULT '',
            default_weight DECIMAL(4,3) DEFAULT 0.0,
            rubric         JSONB DEFAULT '{}',
            is_locked      BOOLEAN DEFAULT FALSE,
            created_by     TEXT DEFAULT 'system',
            created_at     TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS org_settings (
            org_id                          TEXT        PRIMARY KEY,
            quality_tier                    TEXT        NOT NULL DEFAULT 'balanced',
            use_hyde                        BOOLEAN     NOT NULL DEFAULT FALSE,
            use_reranking                   BOOLEAN     NOT NULL DEFAULT TRUE,
            use_query_rewriting             BOOLEAN     NOT NULL DEFAULT TRUE,
            use_hybrid_search               BOOLEAN     NOT NULL DEFAULT FALSE,
            reranker_provider               TEXT        NOT NULL DEFAULT 'cohere',
            retrieval_top_k                 INTEGER     NOT NULL DEFAULT 5,
            rerank_top_n                    INTEGER     NOT NULL DEFAULT 3,
            mandatory_check_use_llm_verify  BOOLEAN     NOT NULL DEFAULT TRUE,
            confidence_retry_threshold      NUMERIC(3,2) NOT NULL DEFAULT 0.75,
            score_variance_threshold        NUMERIC(3,2) NOT NULL DEFAULT 0.15,
            rank_margin_threshold           INTEGER     NOT NULL DEFAULT 3,
            llm_temperature                 NUMERIC(3,2) NOT NULL DEFAULT 0.10,
            output_tone                     TEXT        NOT NULL DEFAULT 'formal',
            output_language                 TEXT        NOT NULL DEFAULT 'en-GB',
            citation_style                  TEXT        NOT NULL DEFAULT 'inline',
            include_confidence_score        BOOLEAN     NOT NULL DEFAULT TRUE,
            include_evidence_quotes         BOOLEAN     NOT NULL DEFAULT TRUE,
            max_evidence_quote_chars        INTEGER     NOT NULL DEFAULT 300,
            parallel_vendors                BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by                      TEXT,
            CHECK (confidence_retry_threshold BETWEEN 0 AND 1),
            CHECK (score_variance_threshold   BETWEEN 0 AND 1),
            CHECK (rank_margin_threshold      BETWEEN 0 AND 100),
            CHECK (llm_temperature            BETWEEN 0 AND 2),
            CHECK (output_tone IN ('formal','conversational','technical')),
            CHECK (citation_style IN ('inline','footnote','appendix')),
            CHECK (reranker_provider IN ('cohere','bge','colbert','none')),
            CHECK (max_evidence_quote_chars BETWEEN 50 AND 2000)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS org_settings_audit (
            audit_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        TEXT        NOT NULL,
            changed_by    TEXT        NOT NULL,
            changed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            field_name    TEXT        NOT NULL,
            old_value     TEXT,
            new_value     TEXT
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS retrieval_log (
            log_id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id             UUID        REFERENCES evaluation_runs(run_id) ON DELETE SET NULL,
            org_id             UUID        NOT NULL,
            vendor_id          TEXT        NOT NULL,
            criterion_id       TEXT,
            query_text         TEXT        NOT NULL,
            rewritten_query    TEXT,
            retrieval_strategy TEXT        NOT NULL,
            chunks             JSONB       NOT NULL DEFAULT '[]',
            scores             JSONB       NOT NULL DEFAULT '{}',
            timing_ms          INTEGER,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_setups_org_rfp ON evaluation_setups(org_id, rfp_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_runs_org_rfp ON evaluation_runs(org_id, rfp_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_vendor_docs_org_vendor ON vendor_documents(org_id, vendor_id, rfp_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_certs_org_vendor ON extracted_certifications(org_id, vendor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_insurance_org_vendor ON extracted_insurance(org_id, vendor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_slas_org_vendor ON extracted_slas(org_id, vendor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_projects_org_vendor ON extracted_projects(org_id, vendor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_pricing_org_vendor ON extracted_pricing(org_id, vendor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_facts_org_vendor ON extracted_facts(org_id, vendor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_facts_setup_target ON extracted_facts(setup_id, target_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_facts_numeric ON extracted_facts(org_id, vendor_id, target_id, numeric_value) WHERE numeric_value IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_run ON audit_log(run_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_org ON audit_log(org_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_org ON users(org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_org_settings_audit_org ON org_settings_audit(org_id, changed_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_retrieval_log_run ON retrieval_log(run_id, criterion_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_retrieval_log_org_vendor ON retrieval_log(org_id, vendor_id, created_at)")

    # Row level security
    for table in [
        "evaluation_setups", "evaluation_runs", "vendor_documents",
        "extracted_certifications", "extracted_insurance", "extracted_slas",
        "extracted_projects", "extracted_pricing", "extracted_facts",
        "decisions", "audit_overrides", "approvals", "audit_log",
        "users", "org_criteria_templates", "dept_criteria_templates",
        "org_settings", "org_settings_audit",
    ]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    # Drop in reverse dependency order
    tables = [
        "retrieval_log", "org_settings_audit", "org_settings",
        "dept_criteria_templates", "org_criteria_templates",
        "tenant_billing", "tenant_modules", "users",
        "audit_log", "approvals", "audit_overrides", "decisions",
        "extracted_facts", "extracted_pricing", "extracted_projects",
        "extracted_slas", "extracted_insurance", "extracted_certifications",
        "vendor_documents", "evaluation_runs", "evaluation_setups",
        "agent_registry", "organisations",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
