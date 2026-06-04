-- app/db/schema.sql
-- Run via: psql -U platformuser -d agenticplatform -h localhost -f app/db/schema.sql
--
-- DESIGN DECISIONS:
-- 1. Users and authorisation are in a SEPARATE SKILL (Skill 01b).
--    This file does not create users or auth tables.
-- 2. EvaluationSetup is persisted as a JSONB blob — simple, no child tables.
-- 3. Five typed extraction tables stay for standard procurement facts
--    where typed SQL columns enable meaningful comparisons (e.g. amount_gbp >= 2000000).
-- 4. extracted_facts is the PRIMARY store for customer-defined criteria.
--    It links to ExtractionTarget.target_id and EvaluationSetup.setup_id.
--    Every department uses this table for their custom criteria.

-- ── Core tables ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS organisations (
    org_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_name          TEXT NOT NULL,
    industry          TEXT,
    subscription_tier TEXT DEFAULT 'starter',
    created_at        TIMESTAMPTZ DEFAULT now(),
    is_active         BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS agent_registry (
    agent_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID REFERENCES organisations(org_id),
    agent_name   TEXT NOT NULL,
    agent_type   TEXT NOT NULL,   -- "procurement" | "hr" | "legal" | "finance" | "custom"
    department   TEXT,            -- department this agent serves
    config       JSONB NOT NULL,  -- AgentConfig JSON — department criteria template
    is_active    BOOLEAN DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now()
);

-- ── EvaluationSetup — persists what the customer confirmed on Page 4b ─
-- Stored as JSONB blob. The Planner reads this. Auditors can reproduce
-- exactly what criteria were used for any completed evaluation.

CREATE TABLE IF NOT EXISTS evaluation_setups (
    setup_id       TEXT PRIMARY KEY,           -- matches EvaluationSetup.setup_id
    org_id         UUID NOT NULL,
    department     TEXT NOT NULL,
    rfp_id         TEXT NOT NULL,
    setup_json     JSONB NOT NULL,             -- full EvaluationSetup as JSON
    confirmed_by   TEXT NOT NULL,              -- user_id who confirmed
    confirmed_at   TIMESTAMPTZ,
    source         TEXT NOT NULL,              -- "department_template" | "rfp_extracted" | "mixed"
    created_at     TIMESTAMPTZ DEFAULT now()
);

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
    currency         TEXT NOT NULL DEFAULT 'GBP',
    approval_tier    INTEGER,
    langsmith_trace  TEXT,
    agent_events     JSONB NOT NULL DEFAULT '[]',
    agent_log        JSONB NOT NULL DEFAULT '[]',
    decision_output  JSONB,
    explanation_output JSONB,        -- Phase 7: narratives + report fields for the customer PDF report
    vendor_names     JSONB DEFAULT '{}',
    created_at       TIMESTAMPTZ DEFAULT now(),
    completed_at     TIMESTAMPTZ,
    created_by_email TEXT,          -- email of the user who started this run (RBAC)
    creator_dept_id  TEXT,          -- dept_id from JWT at creation time (RBAC)
    gaps_report      JSONB          -- detect_and_fill_gaps() output; read by the run-results route
);
-- Idempotent for already-created DBs (CREATE TABLE IF NOT EXISTS skips columns).
ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS gaps_report JSONB;

-- ── Access audit log ───────────────────────────────────────────────────
-- Records who viewed or acted on a run. Append-only, RLS-protected.

CREATE TABLE IF NOT EXISTS access_audit_log (
    log_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    run_id       UUID REFERENCES evaluation_runs(run_id) ON DELETE SET NULL,
    accessed_by  TEXT NOT NULL,
    action       TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_access_audit_log_run_id ON access_audit_log(run_id);
CREATE INDEX IF NOT EXISTS ix_access_audit_log_org_id ON access_audit_log(org_id);

ALTER TABLE access_audit_log ENABLE ROW LEVEL SECURITY;

-- ── Vendor documents ──────────────────────────────────────────────────

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
);

-- ── Standard typed extraction tables ─────────────────────────────────
-- These five tables stay for standard procurement facts.
-- Typed columns (amount_gbp, valid_until, uptime_percentage) enable
-- SQL comparisons: WHERE amount_gbp >= 2000000, WHERE valid_until > now()
-- Every row links back to Qdrant via source_chunk_id.

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
    status          TEXT,          -- current | pending | expired | not_mentioned
    confidence      FLOAT,
    grounding_quote TEXT NOT NULL,
    source_chunk_id TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);

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
);

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
);

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
);

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
);

-- ── extracted_facts — PRIMARY store for customer-defined criteria ─────
-- This is where ALL department-specific and custom criteria land.
-- A logistics evaluation stores fleet_size here.
-- An HR evaluation stores payroll_volume here.
-- A legal evaluation stores qualified_lawyer_headcount here.
-- Links to ExtractionTarget.target_id and EvaluationSetup.setup_id.
-- Supports SQL comparisons via numeric_value and boolean_value.

CREATE TABLE IF NOT EXISTS extracted_facts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID REFERENCES vendor_documents(doc_id),
    org_id          UUID NOT NULL,
    vendor_id       TEXT NOT NULL,
    setup_id        TEXT REFERENCES evaluation_setups(setup_id),
    target_id       TEXT NOT NULL,     -- ExtractionTarget.target_id
    fact_type       TEXT NOT NULL,     -- mirrors ExtractionTarget.fact_type
    fact_name       TEXT NOT NULL,     -- human readable: "UK delivery locations"
    text_value      TEXT,              -- raw extracted text
    numeric_value   NUMERIC,           -- for SQL comparison: fleet_size >= 100
    boolean_value   BOOLEAN,           -- for yes/no: has_uk_presence = true
    unit            TEXT,              -- "vehicles" | "percent" | "GBP" | "months"
    confidence      FLOAT,
    grounding_quote TEXT NOT NULL,     -- REQUIRED — verbatim from source
    source_chunk_id TEXT NOT NULL,     -- links to Qdrant point
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Audit and decision tables ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS decisions (
    decision_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID REFERENCES evaluation_runs(run_id),
    org_id          UUID NOT NULL,
    vendor_id       TEXT,
    decision_type   TEXT,              -- "compliance" | "score" | "ranking" | "final"
    check_id        TEXT,              -- links to MandatoryCheck.check_id
    criterion_id    TEXT,              -- links to ScoringCriterion.criterion_id
    decision        TEXT,              -- "pass" | "fail" | "insufficient_evidence"
    score_value     NUMERIC,
    confidence      FLOAT,
    reasoning       TEXT,
    evidence_quote  TEXT,
    source_doc      TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

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
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         UUID REFERENCES evaluation_runs(run_id),
    org_id         UUID NOT NULL,
    approval_tier  INTEGER NOT NULL,
    approver_role  TEXT NOT NULL,
    status         TEXT DEFAULT 'pending',  -- pending | approved | rejected | expired
    comments       TEXT,
    requested_at   TIMESTAMPTZ DEFAULT now(),
    responded_at   TIMESTAMPTZ,
    sla_deadline   TIMESTAMPTZ
);

-- ── Row level security ────────────────────────────────────────────────
-- Policies enforce org isolation at the database level.
-- Even if application code has a bug, the database rejects cross-org queries.
-- app.current_org_id is set per request in FastAPI middleware.

ALTER TABLE evaluation_setups        ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_runs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_documents         ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_certifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_insurance      ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_slas           ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_projects       ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_pricing        ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_facts          ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisions                ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_overrides          ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals                ENABLE ROW LEVEL SECURITY;

-- org isolation policy — same pattern for every table
-- CREATE POLICY IF NOT EXISTS is PostgreSQL 17+ only.
-- Use DO blocks for idempotency on PostgreSQL 15.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_evaluation_setups') THEN
        CREATE POLICY rls_evaluation_setups ON evaluation_setups
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_evaluation_runs') THEN
        CREATE POLICY rls_evaluation_runs ON evaluation_runs
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_vendor_docs') THEN
        CREATE POLICY rls_vendor_docs ON vendor_documents
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_certifications') THEN
        CREATE POLICY rls_certifications ON extracted_certifications
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_insurance') THEN
        CREATE POLICY rls_insurance ON extracted_insurance
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_slas') THEN
        CREATE POLICY rls_slas ON extracted_slas
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_projects') THEN
        CREATE POLICY rls_projects ON extracted_projects
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_pricing') THEN
        CREATE POLICY rls_pricing ON extracted_pricing
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_extracted_facts') THEN
        CREATE POLICY rls_extracted_facts ON extracted_facts
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_decisions') THEN
        CREATE POLICY rls_decisions ON decisions
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_audit_overrides') THEN
        CREATE POLICY rls_audit_overrides ON audit_overrides
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_approvals') THEN
        CREATE POLICY rls_approvals ON approvals
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
END $$;

-- ── Indexes ───────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_setups_org_rfp
    ON evaluation_setups(org_id, rfp_id);

CREATE INDEX IF NOT EXISTS idx_runs_org_rfp
    ON evaluation_runs(org_id, rfp_id, status);

CREATE INDEX IF NOT EXISTS idx_vendor_docs_org_vendor
    ON vendor_documents(org_id, vendor_id, rfp_id);

CREATE INDEX IF NOT EXISTS idx_certs_org_vendor
    ON extracted_certifications(org_id, vendor_id);

CREATE INDEX IF NOT EXISTS idx_insurance_org_vendor
    ON extracted_insurance(org_id, vendor_id);

CREATE INDEX IF NOT EXISTS idx_slas_org_vendor
    ON extracted_slas(org_id, vendor_id);

CREATE INDEX IF NOT EXISTS idx_projects_org_vendor
    ON extracted_projects(org_id, vendor_id);

CREATE INDEX IF NOT EXISTS idx_pricing_org_vendor
    ON extracted_pricing(org_id, vendor_id);

-- extracted_facts needs three indexes — queried by setup, target, and vendor
CREATE INDEX IF NOT EXISTS idx_facts_org_vendor
    ON extracted_facts(org_id, vendor_id);

CREATE INDEX IF NOT EXISTS idx_facts_setup_target
    ON extracted_facts(setup_id, target_id);

CREATE INDEX IF NOT EXISTS idx_facts_numeric
    ON extracted_facts(org_id, vendor_id, target_id, numeric_value)
    WHERE numeric_value IS NOT NULL;

-- ── Audit log ─────────────────────────────────────────────────────────────────
-- Append-only. Never UPDATE or DELETE rows. One row per significant event.
-- event_type values:
--   run.created | run.confirmed | run.completed | run.interrupted | run.blocked
--   agent.started | agent.completed | agent.blocked
--   override.submitted | approval.requested | approval.responded

CREATE TABLE IF NOT EXISTS audit_log (
    log_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    run_id      UUID REFERENCES evaluation_runs(run_id) ON DELETE SET NULL,
    event_type  TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'system',
    agent       TEXT,
    detail      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_run ON audit_log(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_org ON audit_log(org_id, created_at);
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- ── SaaS shell tables ──────────────────────────────────────────────────────────

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
);

CREATE INDEX IF NOT EXISTS idx_users_org ON users(org_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_org_isolation ON users
    USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

-- Session allowlist for JWT revocation (E2). One row per issued token (jti).
-- get_current_user checks the row is active on every request, so logout /
-- forced sign-out / password reset can invalidate a token before it expires.
CREATE TABLE IF NOT EXISTS auth_sessions (
    jti            UUID PRIMARY KEY,
    user_id        UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    org_id         UUID NOT NULL REFERENCES organisations(org_id) ON DELETE CASCADE,
    issued_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ NOT NULL,
    revoked_at     TIMESTAMPTZ,
    revoked_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_active
    ON auth_sessions(jti) WHERE revoked_at IS NULL;
ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_auth_sessions') THEN
        CREATE POLICY rls_auth_sessions ON auth_sessions
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
END $$;

-- One-time, expiring tokens for invite-acceptance and password-reset (E2).
-- Only the SHA-256 hash of the token is stored; the plaintext lives solely in
-- the link handed to the user. Single-use is enforced via used_at.
CREATE TABLE IF NOT EXISTS auth_onetime_tokens (
    token_hash  TEXT PRIMARY KEY,
    purpose     TEXT NOT NULL CHECK (purpose IN ('invite', 'password_reset')),
    email       TEXT NOT NULL,
    org_id      UUID REFERENCES organisations(org_id) ON DELETE CASCADE,
    role        TEXT,
    dept_id     UUID,
    user_id     UUID REFERENCES users(user_id) ON DELETE CASCADE,
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_auth_onetime_email
    ON auth_onetime_tokens(purpose, email) WHERE used_at IS NULL;
ALTER TABLE auth_onetime_tokens ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_auth_onetime_tokens') THEN
        -- org_id is NULL until a reset token is bound to a known user's org; the
        -- predicate matches a set org and the identity path uses the owner role.
        CREATE POLICY rls_auth_onetime_tokens ON auth_onetime_tokens
            USING (org_id IS NULL
                   OR org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS tenant_modules (
    org_id       UUID NOT NULL REFERENCES organisations(org_id) ON DELETE CASCADE,
    module_key   TEXT NOT NULL,
    enabled      BOOLEAN NOT NULL DEFAULT FALSE,
    config       JSONB NOT NULL DEFAULT '{}',
    activated_at TIMESTAMPTZ,
    PRIMARY KEY (org_id, module_key)
);

CREATE TABLE IF NOT EXISTS tenant_billing (
    org_id                 UUID PRIMARY KEY REFERENCES organisations(org_id) ON DELETE CASCADE,
    stripe_customer_id     TEXT,
    stripe_subscription_id TEXT,
    plan                   TEXT NOT NULL DEFAULT 'trial'
                               CHECK (plan IN ('trial','starter','professional','enterprise')),
    modules_active         TEXT[] NOT NULL DEFAULT '{}',
    next_billing           TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS org_criteria_templates (
    template_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES organisations(org_id)
                   ON DELETE CASCADE,
    check_type     TEXT NOT NULL
                   CHECK (check_type IN ('mandatory','scoring')),
    name           TEXT NOT NULL,
    description    TEXT DEFAULT '',
    what_passes    TEXT DEFAULT '',
    default_weight DECIMAL(4,3) DEFAULT 0.0,
    rubric         JSONB DEFAULT '{}',
    applies_to     TEXT DEFAULT 'all',
    is_locked      BOOLEAN DEFAULT FALSE,
    created_by     TEXT DEFAULT 'system',
    created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dept_criteria_templates (
    template_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL REFERENCES organisations(org_id)
                   ON DELETE CASCADE,
    department     TEXT NOT NULL,
    check_type     TEXT NOT NULL
                   CHECK (check_type IN ('mandatory','scoring')),
    name           TEXT NOT NULL,
    description    TEXT DEFAULT '',
    what_passes    TEXT DEFAULT '',
    default_weight DECIMAL(4,3) DEFAULT 0.0,
    rubric         JSONB DEFAULT '{}',
    is_locked      BOOLEAN DEFAULT FALSE,
    created_by     TEXT DEFAULT 'system',
    created_at     TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE org_criteria_templates ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename='org_criteria_templates'
    AND policyname='org_criteria_isolation'
  ) THEN
    CREATE POLICY org_criteria_isolation
    ON org_criteria_templates
    USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
  END IF;
END $$;

ALTER TABLE dept_criteria_templates ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename='dept_criteria_templates'
    AND policyname='dept_criteria_isolation'
  ) THEN
    CREATE POLICY dept_criteria_isolation
    ON dept_criteria_templates
    USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
  END IF;
END $$;

-- ── org_settings — per-org configuration overrides ──────────────────────────

CREATE TABLE IF NOT EXISTS org_settings (
    org_id                          TEXT        PRIMARY KEY,
    quality_tier                    TEXT        NOT NULL DEFAULT 'balanced',

    use_hyde                        BOOLEAN     NOT NULL DEFAULT FALSE,
    use_reranking                   BOOLEAN     NOT NULL DEFAULT TRUE,
    use_query_rewriting             BOOLEAN     NOT NULL DEFAULT TRUE,
    use_hybrid_search               BOOLEAN     NOT NULL DEFAULT FALSE,
    reranker_provider               TEXT        NOT NULL DEFAULT 'bge',
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
    CHECK (reranker_provider IN ('cohere','bge','colbert','modal','none')),
    CHECK (max_evidence_quote_chars BETWEEN 50 AND 2000)
);

CREATE TABLE IF NOT EXISTS org_settings_audit (
    audit_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        TEXT        NOT NULL,
    changed_by    TEXT        NOT NULL,
    changed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    field_name    TEXT        NOT NULL,
    old_value     TEXT,
    new_value     TEXT
);

CREATE INDEX IF NOT EXISTS idx_org_settings_audit_org
    ON org_settings_audit(org_id, changed_at DESC);

ALTER TABLE org_settings       ENABLE ROW LEVEL SECURITY;
ALTER TABLE org_settings_audit ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename='org_settings' AND policyname='org_settings_isolation'
  ) THEN
    CREATE POLICY org_settings_isolation ON org_settings
        USING (org_id = current_setting('app.current_org_id', true));
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename='org_settings_audit' AND policyname='org_settings_audit_isolation'
  ) THEN
    CREATE POLICY org_settings_audit_isolation ON org_settings_audit
        USING (org_id = current_setting('app.current_org_id', true));
  END IF;
END $$;

-- ── Retrieval log — one row per retrieval call ────────────────────────────────
-- Makes "what did the system see for this criterion on this run" a single SQL query.
-- Never UPDATE or DELETE rows.

CREATE TABLE IF NOT EXISTS retrieval_log (
    log_id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id             UUID        REFERENCES evaluation_runs(run_id) ON DELETE SET NULL,
    org_id             UUID        NOT NULL,
    vendor_id          TEXT        NOT NULL,
    criterion_id       TEXT,                    -- criterion_id or check name; NULL for ad-hoc
    query_text         TEXT        NOT NULL,
    rewritten_query    TEXT,
    retrieval_strategy TEXT        NOT NULL,
    chunks             JSONB       NOT NULL DEFAULT '[]',
    scores             JSONB       NOT NULL DEFAULT '{}',
    timing_ms          INTEGER,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_log_run
    ON retrieval_log(run_id, criterion_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_log_org_vendor
    ON retrieval_log(org_id, vendor_id, created_at);

-- ═══════════════════════════════════════════════════════════════════════
-- Phase 9 — Multi-user RFP visibility & collaboration
-- ═══════════════════════════════════════════════════════════════════════
-- Adds matrix department membership, explicit collaborator invites, and
-- approval-queue assignments. The runs_visible_to() function below uses
-- all three (plus role + ownership) to compute what each user can see.
--
-- INVARIANT: autonomous ingestion (Phase 5 watchers) must NEVER write to
-- these tables. Access lists are decided when the RFP is created by a
-- human; file arrival is data, not access.

-- Matrix membership — a user can belong to multiple departments
CREATE TABLE IF NOT EXISTS user_departments (
    user_id        UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    department_id  TEXT NOT NULL,
    role_in_dept   TEXT NOT NULL DEFAULT 'member'
                       CHECK (role_in_dept IN ('member','lead','observer')),
    added_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, department_id)
);

CREATE INDEX IF NOT EXISTS idx_user_departments_dept
    ON user_departments(department_id);

-- Explicit collaborator invites on a specific evaluation run
CREATE TABLE IF NOT EXISTS rfp_collaborators (
    run_id     UUID NOT NULL REFERENCES evaluation_runs(run_id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role       TEXT NOT NULL DEFAULT 'viewer'
                   CHECK (role IN ('viewer','reviewer','editor')),
    added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    added_by   UUID REFERENCES users(user_id) ON DELETE SET NULL,
    PRIMARY KEY (run_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_rfp_collaborators_user
    ON rfp_collaborators(user_id);

-- Approval queue — which user must sign off on which run
CREATE TABLE IF NOT EXISTS approval_assignments (
    run_id            UUID NOT NULL REFERENCES evaluation_runs(run_id) ON DELETE CASCADE,
    approver_user_id  UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    approver_role     TEXT NOT NULL,   -- 'cfo' | 'cto' | 'cpo' | 'legal' | etc.
    status            TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending','approved','rejected')),
    assigned_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at       TIMESTAMPTZ,
    comment           TEXT,
    PRIMARY KEY (run_id, approver_user_id)
);

CREATE INDEX IF NOT EXISTS idx_approval_assignments_user_pending
    ON approval_assignments(approver_user_id, status)
    WHERE status = 'pending';

-- RLS on the three new tables — org isolation via the joined evaluation_runs/users
ALTER TABLE user_departments     ENABLE ROW LEVEL SECURITY;
ALTER TABLE rfp_collaborators    ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_assignments ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_user_departments') THEN
        CREATE POLICY rls_user_departments ON user_departments
            USING (EXISTS (
                SELECT 1 FROM users u
                WHERE u.user_id = user_departments.user_id
                  AND u.org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
            ));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_rfp_collaborators') THEN
        CREATE POLICY rls_rfp_collaborators ON rfp_collaborators
            USING (EXISTS (
                SELECT 1 FROM evaluation_runs r
                WHERE r.run_id = rfp_collaborators.run_id
                  AND r.org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
            ));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_approval_assignments') THEN
        CREATE POLICY rls_approval_assignments ON approval_assignments
            USING (EXISTS (
                SELECT 1 FROM evaluation_runs r
                WHERE r.run_id = approval_assignments.run_id
                  AND r.org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
            ));
    END IF;
END $$;

-- ── runs_visible_to() — central authorisation function ─────────────────
-- Returns the set of evaluation_runs that a given user is permitted to see.
-- Default-deny: if no predicate matches, the user sees nothing.
--
-- Predicates (OR'd):
--   1. Wide org-level role (platform_admin, company_admin)
--   2. User created the run                  (created_by_email match)
--   3. User belongs to the run's department  (user_departments join)
--   4. User was explicitly invited           (rfp_collaborators join)
--   5. User is an assigned approver          (approval_assignments join)

CREATE OR REPLACE FUNCTION runs_visible_to(
    p_user_id    UUID,
    p_user_email TEXT,
    p_user_role  TEXT,
    p_org_id     UUID
)
RETURNS SETOF evaluation_runs AS $$
    SELECT r.* FROM evaluation_runs r
    WHERE r.org_id = p_org_id
      AND (
        p_user_role IN ('platform_admin', 'company_admin')
        OR r.created_by_email = p_user_email
        OR r.creator_dept_id IN (
            SELECT department_id FROM user_departments WHERE user_id = p_user_id
        )
        OR EXISTS (
            SELECT 1 FROM rfp_collaborators c
            WHERE c.run_id = r.run_id AND c.user_id = p_user_id
        )
        OR EXISTS (
            SELECT 1 FROM approval_assignments a
            WHERE a.run_id = r.run_id AND a.approver_user_id = p_user_id
        )
      );
$$ LANGUAGE SQL STABLE;

-- ── Phase 5 — Background ingestion foundation ────────────────────────
-- See docs/dev/PRODUCTION_READINESS_PLAN.md Phase 5.0.

CREATE TABLE IF NOT EXISTS rfps (
    rfp_id              TEXT PRIMARY KEY,
    org_id              UUID NOT NULL,
    title               TEXT NOT NULL,
    department          TEXT,
    created_by_email    TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    submission_deadline TIMESTAMPTZ,
    submission_status   TEXT NOT NULL DEFAULT 'open'
        CHECK (submission_status IN ('open','closed','processing','facts_ready','evaluated')),
    autonomy_mode       TEXT NOT NULL DEFAULT 'auto_to_evaluate'
        CHECK (autonomy_mode IN ('manual','auto_to_evaluate','auto_to_report'))
);
CREATE INDEX IF NOT EXISTS ix_rfps_org ON rfps(org_id);
CREATE INDEX IF NOT EXISTS ix_rfps_deadline_open
    ON rfps(submission_deadline)
    WHERE submission_status = 'open';

CREATE TABLE IF NOT EXISTS invited_vendors (
    rfp_id      TEXT NOT NULL REFERENCES rfps(rfp_id) ON DELETE CASCADE,
    vendor_id   TEXT NOT NULL,
    vendor_name TEXT,
    invited_by  TEXT NOT NULL,
    invited_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (rfp_id, vendor_id)
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                 UUID NOT NULL,
    rfp_id                 TEXT NOT NULL,
    vendor_id              TEXT NOT NULL,
    source_uri             TEXT,
    filename               TEXT,
    content_hash           CHAR(64) NOT NULL,
    status                 TEXT NOT NULL
        CHECK (status IN (
            'received','superseded','queued','processing','facts_ready',
            'failed','duplicate','needs_attribution','rejected_late'
        )),
    attribution_confidence FLOAT,
    received_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempted_at           TIMESTAMPTZ,
    completed_at           TIMESTAMPTZ,
    error                  TEXT,
    doc_id                 UUID REFERENCES vendor_documents(doc_id),
    superseded_by          UUID REFERENCES ingestion_jobs(job_id),
    UNIQUE (rfp_id, vendor_id, content_hash)
);
CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_rfp_status
    ON ingestion_jobs(rfp_id, status);

CREATE TABLE IF NOT EXISTS event_log (
    event_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type   TEXT NOT NULL,
    org_id       UUID NOT NULL,
    rfp_id       TEXT NOT NULL,
    payload      JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_event_log_pending
    ON event_log(created_at) WHERE delivered_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_event_log_rfp ON event_log(rfp_id);

-- ── Phase 3 — LLM response cache ─────────────────────────────────────
-- Content-addressed cache for `call_llm()` responses. Tenant-blind on
-- purpose — see docs/dev/PRODUCTION_READINESS_PLAN.md Phase 3 "Tenant
-- blindness" subsection. Do NOT add an org_id column.

CREATE TABLE IF NOT EXISTS llm_response_cache (
    cache_key         TEXT PRIMARY KEY,
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    response          TEXT NOT NULL,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_hit_at       TIMESTAMPTZ,
    hit_count         INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_llm_cache_created ON llm_response_cache(created_at);
CREATE INDEX IF NOT EXISTS idx_llm_cache_model   ON llm_response_cache(model);

-- ════════════════════════════════════════════════════════════════════════════
-- TENANT ISOLATION — make Row-Level Security actually bite (P0.16)
-- ════════════════════════════════════════════════════════════════════════════
-- Two things were missing before, which made every RLS policy above inert:
--   1. audit_log and access_audit_log had RLS ENABLED but NO policy — under a
--      non-owner role that means deny-all, so they get policies here.
--   2. The application connected as the table OWNER (a superuser), and Postgres
--      exempts the owner/superuser from RLS unless FORCE is set. We now (a)
--      FORCE RLS on every protected table AND (b) introduce a dedicated
--      NON-superuser, NON-owner login role `platform_app` that the app connects
--      as at runtime. Either alone is insufficient; together RLS is enforced.
-- The owner role (platformuser) is still used for DDL/migrations, identity/auth
-- lookups, and cross-org system jobs — see app/db/session.py.

-- 1 ── policies for the two audit tables that lacked them ────────────────────
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_audit_log') THEN
        CREATE POLICY rls_audit_log ON audit_log
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_access_audit_log') THEN
        CREATE POLICY rls_access_audit_log ON access_audit_log
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
END $$;

-- 2 ── operational tables that hold tenant data — bring under RLS too ───────
-- These were app-filter-only before. invited_vendors is keyed by rfp_id (no
-- org_id) so it isolates via a join to its RFP.
ALTER TABLE rfps            ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_log       ENABLE ROW LEVEL SECURITY;
ALTER TABLE invited_vendors ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_rfps') THEN
        CREATE POLICY rls_rfps ON rfps
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_ingestion_jobs') THEN
        CREATE POLICY rls_ingestion_jobs ON ingestion_jobs
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_event_log') THEN
        CREATE POLICY rls_event_log ON event_log
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_invited_vendors') THEN
        CREATE POLICY rls_invited_vendors ON invited_vendors
            USING (EXISTS (SELECT 1 FROM rfps r
                           WHERE r.rfp_id = invited_vendors.rfp_id
                             AND r.org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid));
    END IF;
END $$;

-- 3 ── FORCE RLS on EVERY table that has RLS enabled ─────────────────────────
-- Dynamic so there is ONE source of truth (the set of RLS-enabled tables) and
-- a new protected table is force-secured automatically. FORCE makes the policy
-- apply even to the table owner — defence in depth behind the non-owner role.
DO $$
DECLARE t regclass;
BEGIN
    FOR t IN
        SELECT oid FROM pg_class
        WHERE relrowsecurity = true AND relnamespace = 'public'::regnamespace
    LOOP
        EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', t);
    END LOOP;
END $$;

-- 4 ── dedicated non-superuser application role ──────────────────────────────
-- Created WITHOUT a password literal. The password is set out-of-band from the
-- POSTGRES_APP_PASSWORD secret — run schema.sql via:
--     psql -v app_pw="$POSTGRES_APP_PASSWORD" -f app/db/schema.sql
-- (Alembic migration 0011 reads the same env var.) No credential lives in git.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_app') THEN
        CREATE ROLE platform_app LOGIN
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END $$;
-- :'app_pw' is substituted by psql (outside any dollar-quote). If you ran this
-- file without -v app_pw=…, set the password manually afterwards.
ALTER ROLE platform_app PASSWORD :'app_pw';

GRANT USAGE ON SCHEMA public TO platform_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO platform_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO platform_app;
-- Cover tables/sequences created by future migrations (run as the owner).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO platform_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO platform_app;
