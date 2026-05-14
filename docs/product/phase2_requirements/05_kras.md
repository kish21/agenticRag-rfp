# KRAs — Key Result Areas
*Version 1.0 — 2026-05-14*

---

## Purpose

KRAs define the accountability areas for the engineering and product team building this platform. Each KRA maps to a system component with a clear owner, measurable outcome, and the files responsible for delivering it.

This document is relevant for:
- Tech Lead / Founding Engineer interviews (demonstrates ownership scope)
- Team scaling (defines what roles to hire)
- Performance review structure for the engineering team

---

## KRA Map

| KRA | Area | Owner Level | Key Files |
|---|---|---|---|
| KRA-1 | Agent Architecture & Orchestration | Senior AI Engineer / Tech Lead | `app/agents/*.py`, `app/core/output_models.py` |
| KRA-2 | Retrieval Quality | AI Engineer | `app/agents/retrieval.py`, `app/core/reranker_provider.py`, `app/core/hyde.py`, `app/core/query_rewriter.py` |
| KRA-3 | Extraction Accuracy & Data Integrity | AI Engineer | `app/agents/extraction.py`, `app/db/fact_store.py`, `app/db/schema.sql` |
| KRA-4 | Platform Configurability | Senior Engineer | `app/core/llm_provider.py`, `app/core/embedding_provider.py`, `app/core/reranker_provider.py`, `app/core/observability_provider.py` |
| KRA-5 | Observability & Monitoring | Engineer | `app/core/observability_provider.py`, `app/jobs/rate_monitor.py`, `app/jobs/cleanup.py` |
| KRA-6 | Multi-Tenancy & Security | Senior Engineer | `app/core/auth.py`, `app/api/routes.py`, `app/db/schema.sql` (RLS), `app/core/org_settings.py` |
| KRA-7 | CEO Dashboard & Frontend | Frontend Engineer | `frontend/` (Next.js), `app/api/admin_routes.py` |
| KRA-8 | Governance & Audit | Engineer | `app/core/override_mechanism.py`, `app/core/audit.py`, `app/core/rfp_confirmation.py` |
| KRA-9 | Infrastructure & Deployment | DevOps / Engineer | `app_modal.py`, `docker-compose.yml`, `app/config/platform.yaml` |

---

## KRA Detail

### KRA-1 — Agent Architecture & Orchestration

**Accountability:** Design and maintain the 9-agent LangGraph pipeline. Ensure every agent has a typed Pydantic output model. Ensure Critic Agent runs after every agent. Own the agent DAG topology.

**Success looks like:**
- All 9 agents have Pydantic output models in `output_models.py`
- Critic Agent cannot be bypassed — pipeline topology enforces it
- No agent passes raw text to another agent
- Agent registry (`agent_registry.py`) reflects current pipeline state

**Failure signals:**
- Any agent returning a dict instead of a Pydantic model
- A new agent added without a corresponding Critic check
- Hardcoded thresholds discovered inside agent files

---

### KRA-2 — Retrieval Quality

**Accountability:** Own the end-to-end retrieval pipeline: query rewriting, HyDE, hybrid search (dense + sparse), RRF fusion, reranking. Own the retrieval precision and recall metrics.

**Success looks like:**
- Retrieval Critic reports adequate evidence for >90% of criteria on the test set
- Reranker raises relevant chunk from position 15 to position ≤3 in benchmark tests
- HyDE measurably improves retrieval recall on abstract procurement criteria

**Failure signals:**
- Retrieval Critic frequently reporting inadequate evidence despite relevant content existing in the document
- Reranker provider change breaking the retrieval pipeline
- Hardwired embedding model discovered in retrieval code

---

### KRA-3 — Extraction Accuracy & Data Integrity

**Accountability:** Own the extraction pipeline: structured fact extraction from retrieved chunks, grounding quote validation, PostgreSQL fact storage. Own the hallucination rate metric.

**Success looks like:**
- All extracted facts have a non-empty grounding_quote that passes verbatim containment check
- Extraction error rate (wrong fact type, misread value) < 5% on held-out test set
- Every fact row has a source_chunk_id linking back to Qdrant

**Failure signals:**
- Grounding quote check failing after a PDF parsing change
- Whitespace normalisation fix reverted (causing false hallucination blocks on table-format PDFs)
- Facts written without source_chunk_id

---

### KRA-4 — Platform Configurability

**Accountability:** Own the provider abstraction layer: LLM, embedding, reranker, observability, compute. Guarantee that swapping any provider requires only a .env file change.

**Success looks like:**
- Six LLM providers supported, tested, documented
- Four embedding providers supported, tested, documented
- Four reranker providers supported, tested, documented
- Three observability providers supported, tested, documented
- Zero provider SDK imports outside the designated provider files

**Failure signals:**
- Direct `from openai import` discovered in an agent file
- Provider swap requiring code changes
- Embedding dimension mismatch after provider switch (missing re-ingestion warning)

---

### KRA-5 — Observability & Monitoring

**Accountability:** Own the observability stack: LangSmith passive tracing, LangFuse agent logging, rate monitor, cleanup jobs. Ensure every LLM call and every Critic flag is traceable.

**Success looks like:**
- Every LLM call traceable in LangSmith by run_id
- Every Critic flag logged with: agent name, flag type, reason, timestamp
- Rate monitor fires a log alert when LLM usage exceeds 80% of limit
- Cleanup job purges expired runs without manual intervention

**Failure signals:**
- Observability provider import failure silently drops logs instead of erroring
- Critic flags logged without run_id (makes debugging impossible)
- Rate monitor not running (discovered via missed limit breach)

---

### KRA-6 — Multi-Tenancy & Security

**Accountability:** Own tenant isolation: JWT auth, org_id injection, PostgreSQL Row-Level Security, Qdrant filter enforcement. Own the security model document. Zero cross-tenant leakage is the only acceptable outcome.

**Success looks like:**
- 500 concurrent cross-tenant isolation tests pass with zero leakage
- org_id is injected from JWT — never accepted from request body
- RLS policy active on all PostgreSQL tables containing org data
- All Qdrant queries include org_id filter — no unfiltered collection scans

**Failure signals:**
- Any test demonstrating cross-org data access
- org_id found as a request body parameter in any route
- RLS disabled for a table "just during development"

---

### KRA-7 — CEO Dashboard & Frontend

**Accountability:** Own the Next.js frontend: CEO dashboard, Procurement Manager evaluation UI, approval workflow, PDF report viewer. Own the API endpoints that feed the dashboard.

**Success looks like:**
- CEO dashboard loads in <3 seconds with real data
- Duplicate vendor alert visible on dashboard within 60 seconds of trigger
- Pricing anomaly alert visible without page refresh
- Evaluation report PDF downloadable immediately after pipeline completes

**Failure signals:**
- Dashboard showing stale data (cached more than 30 seconds behind)
- Alert fired in the database but not visible on dashboard
- PDF report accessible without authentication

---

### KRA-8 — Governance & Audit

**Accountability:** Own the governance layer: RFP identity confirmation, human override mechanism, AuditOverride table, 7-year retention policy. Own the compliance documentation.

**Success looks like:**
- Every override creates an immutable AuditOverride record
- Override with empty justification is rejected (422 error)
- RFP identity confirmation step prevents wrong-document errors in >99% of cases
- Audit log exportable via API in < 5 seconds for any run

**Failure signals:**
- Override without audit record discovered
- AuditOverride rows deleted or updated (should be insert-only)
- RFP confirmation step bypassed via direct API call

---

### KRA-9 — Infrastructure & Deployment

**Accountability:** Own the deployment surface: Modal (PDF extraction, batch embedding, LLM inference), Docker Compose (local dev), cloud PostgreSQL and Qdrant (production). Own the deployment runbook.

**Success looks like:**
- `docker-compose up` starts full local stack in <2 minutes
- `modal deploy app_modal.py --env rag` deploys all three images without error
- New LLM_PROVIDER switch requires only .env change, no restart of API server
- Cloud PostgreSQL and Qdrant provisioned and connected for pilot customer

**Failure signals:**
- Modal deploy failing due to SSL / VPN issue (current blocker)
- Local stack requiring manual database migration for new tenant
- Compute provider hardwired to Modal (blocks Azure/AWS customers)
