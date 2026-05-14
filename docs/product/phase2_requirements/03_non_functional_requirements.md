# Non-Functional Requirements
*Version 1.0 — 2026-05-14*

---

## NFR-01: Performance

| ID | Requirement | Rationale |
|---|---|---|
| NFR-01.1 | End-to-end pipeline (3 vendors, 50-page PDFs) shall complete in < 45 minutes | Procurement Manager targets same-day turnaround |
| NFR-01.2 | CEO dashboard shall load initial view in < 3 seconds | Executive users abandon slow dashboards |
| NFR-01.3 | Dashboard data shall refresh within 30 seconds of any pipeline event | Real-time visibility requirement |
| NFR-01.4 | API p95 response time for read endpoints shall be < 500ms | Standard enterprise SLA expectation |
| NFR-01.5 | Embedding batch (200 chunks, Modal A10G) shall complete in < 5 seconds | Ingestion bottleneck |
| NFR-01.6 | LLM calls shall time out after 120 seconds with a logged error — no silent hang | Rate limiter + backoff handles retries |

## NFR-02: Reliability

| ID | Requirement | Rationale |
|---|---|---|
| NFR-02.1 | Pipeline success rate shall be > 99% (excluding planned maintenance) | Enterprise SLA expectation |
| NFR-02.2 | LLM rate limit errors shall be handled with exponential backoff — max 5 retries before escalation | Prevents mid-run failure |
| NFR-02.3 | System shall recover from a single agent failure without losing all pipeline state | LangGraph checkpoint recovery |
| NFR-02.4 | PostgreSQL and Qdrant shall each have automated daily backups with 30-day retention | Data durability requirement |
| NFR-02.5 | Modal GPU cold start (A100, Qwen 2.5 72B) shall be tolerated — pipeline waits up to 10 minutes | vLLM load on cold container |

## NFR-03: Scalability

| ID | Requirement | Rationale |
|---|---|---|
| NFR-03.1 | System shall support parallel evaluation of up to 10 RFP runs simultaneously | Large enterprise concurrent usage |
| NFR-03.2 | Qdrant collection shall support up to 10M vectors per org without degraded retrieval performance | FTSE 250 multi-year document archive |
| NFR-03.3 | PostgreSQL shall support up to 100 concurrent connections without connection pool exhaustion | Multi-department concurrent use |
| NFR-03.4 | Tenant onboarding shall require no schema migration for new orgs | New org inherits defaults from config |

## NFR-04: Security

| ID | Requirement | Rationale |
|---|---|---|
| NFR-04.1 | All API endpoints shall require a valid JWT — no anonymous access | Enterprise authentication baseline |
| NFR-04.2 | org_id shall be injected from JWT server-side — never accepted from request body or query params | Prevents tenant impersonation |
| NFR-04.3 | PostgreSQL Row-Level Security shall enforce org_id isolation at the database layer | Defence in depth — not just API-level |
| NFR-04.4 | Qdrant queries shall always include org_id + vendor_id filters — no unfiltered scans permitted in production code | Tenant isolation in vector store |
| NFR-04.5 | All secrets (API keys, DB credentials) shall be loaded from environment variables — never committed to source | Credential hygiene |
| NFR-04.6 | SSL verification shall be configurable (SSL_VERIFY=false for dev only) — production always uses SSL | Corporate network proxy support |
| NFR-04.7 | All LLM calls shall go through call_llm() — no direct provider SDK imports in agent files | Audit surface control |

## NFR-05: Compliance & Data Governance

| ID | Requirement | Rationale |
|---|---|---|
| NFR-05.1 | All audit records (decisions, overrides, Critic flags) shall be retained for minimum 7 years | UK procurement law + GDPR |
| NFR-05.2 | Audit tables shall be insert-only — no UPDATE or DELETE on audit rows | Immutability requirement |
| NFR-05.3 | Tenant data purge shall be available via admin API — complete deletion in < 1 hour | GDPR right to erasure |
| NFR-05.4 | Data residency: org data shall remain in the configured cloud region — no cross-region replication by default | EU data residency (GDPR Article 46) |
| NFR-05.5 | Every agent output shall be a Pydantic BaseModel — no raw text passed between agents | Structured output integrity |
| NFR-05.6 | Every extracted fact shall have a non-empty grounding_quote — Critic enforces this as a HARD check | Hallucination prevention |

## NFR-06: Observability

| ID | Requirement | Rationale |
|---|---|---|
| NFR-06.1 | Every LLM call shall be traced in LangSmith (passive, via env vars) | Pipeline debugging |
| NFR-06.2 | Every agent run and Critic flag shall be logged to the configured observability provider (LangFuse / stdout / none) | Operational monitoring |
| NFR-06.3 | Observability provider shall be swappable via OBSERVABILITY_PROVIDER env var | Air-gapped deployment support |
| NFR-06.4 | Failed pipeline runs shall generate a structured error log with: run_id, agent_name, error_type, timestamp | On-call diagnostics |
| NFR-06.5 | Rate monitor job shall run every 30 minutes and log LLM usage against configured limits | Cost control |

## NFR-07: Maintainability

| ID | Requirement | Rationale |
|---|---|---|
| NFR-07.1 | All agent business logic thresholds shall be in YAML config files — no magic numbers in Python files | Product can change thresholds without engineering |
| NFR-07.2 | Adding a new LLM provider shall require changes only in llm_provider.py — no other files | Provider abstraction contract |
| NFR-07.3 | All agent outputs shall be Pydantic models defined in output_models.py — no inline model definitions | Single source of truth for contracts |
| NFR-07.4 | Checkpoint runner (checkpoint_runner.py) shall pass all defined checks after every change | Regression prevention |
| NFR-07.5 | Drift detector (drift_detector.py) shall verify no config/code drift after every session | Structural integrity |

## NFR-08: Deployability

| ID | Requirement | Rationale |
|---|---|---|
| NFR-08.1 | Full local dev stack shall start with a single `docker-compose up` command | Developer onboarding |
| NFR-08.2 | LLM provider swap shall require only .env file change — no code change, no restart | Customer self-service |
| NFR-08.3 | New tenant onboarding shall complete via admin API — no manual database steps | Self-service multi-tenancy |
| NFR-08.4 | Modal deployment shall complete with a single `modal deploy` command | Cloud deployment simplicity |
| NFR-08.5 | Air-gapped deployment (COMPUTE_PROVIDER=local_worker) shall require no internet access after initial setup | NHS / government air-gap requirement |
