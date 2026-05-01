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
    confirmed_at   TIMESTAMPTZ NOT NULL,
    source         TEXT NOT NULL,              -- "department_template" | "rfp_extracted" | "mixed"
    created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    setup_id        TEXT REFERENCES evaluation_setups(setup_id),
    rfp_id          TEXT NOT NULL,
    agent_id        UUID REFERENCES agent_registry(agent_id),
    status          TEXT DEFAULT 'running',    -- running | complete | failed | blocked
    vendor_ids      TEXT[],
    contract_value  NUMERIC,
    approval_tier   INTEGER,
    langsmith_trace TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

-- ── Vendor documents ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS vendor_documents (
    doc_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    vendor_id     TEXT NOT NULL,
    rfp_id        TEXT NOT NULL,
    setup_id      TEXT REFERENCES evaluation_setups(setup_id),
    filename      TEXT NOT NULL,
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
            USING (org_id::text = current_setting('app.current_org_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_evaluation_runs') THEN
        CREATE POLICY rls_evaluation_runs ON evaluation_runs
            USING (org_id::text = current_setting('app.current_org_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_vendor_docs') THEN
        CREATE POLICY rls_vendor_docs ON vendor_documents
            USING (org_id::text = current_setting('app.current_org_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_certifications') THEN
        CREATE POLICY rls_certifications ON extracted_certifications
            USING (org_id::text = current_setting('app.current_org_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_insurance') THEN
        CREATE POLICY rls_insurance ON extracted_insurance
            USING (org_id::text = current_setting('app.current_org_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_slas') THEN
        CREATE POLICY rls_slas ON extracted_slas
            USING (org_id::text = current_setting('app.current_org_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_projects') THEN
        CREATE POLICY rls_projects ON extracted_projects
            USING (org_id::text = current_setting('app.current_org_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_pricing') THEN
        CREATE POLICY rls_pricing ON extracted_pricing
            USING (org_id::text = current_setting('app.current_org_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_extracted_facts') THEN
        CREATE POLICY rls_extracted_facts ON extracted_facts
            USING (org_id::text = current_setting('app.current_org_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_decisions') THEN
        CREATE POLICY rls_decisions ON decisions
            USING (org_id::text = current_setting('app.current_org_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_audit_overrides') THEN
        CREATE POLICY rls_audit_overrides ON audit_overrides
            USING (org_id::text = current_setting('app.current_org_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'rls_approvals') THEN
        CREATE POLICY rls_approvals ON approvals
            USING (org_id::text = current_setting('app.current_org_id', true));
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
