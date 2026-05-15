# Functional Requirements Specification
*Version 1.0 — 2026-05-14*

---

## FR-01: Document Ingestion

| ID | Requirement |
|---|---|
| FR-01.1 | System shall accept PDF and DOCX vendor response documents up to 500MB per file |
| FR-01.2 | System shall confirm RFP identity before proceeding (prevents wrong-document errors) |
| FR-01.3 | System shall chunk documents using hierarchical (summary/detail/leaf) and sentence-window strategies |
| FR-01.4 | System shall create dense embeddings (configurable provider) and sparse BM25 embeddings per chunk |
| FR-01.5 | System shall store all chunks in Qdrant, scoped by org_id + vendor_id — no cross-tenant reads |
| FR-01.6 | System shall validate chunk count, embedding dimensions, and collection naming before completing ingestion |
| FR-01.7 | Ingestion agent shall trigger Critic Agent validation after completing; HARD flag shall block pipeline |

## FR-02: Fact Extraction

| ID | Requirement |
|---|---|
| FR-02.1 | System shall extract structured facts into typed PostgreSQL tables: certifications, insurance, SLAs, projects, pricing, generic |
| FR-02.2 | Every extracted fact shall include a `grounding_quote` field containing verbatim text from the source document |
| FR-02.3 | System shall normalise whitespace in grounding quotes before comparison (PDF table cell formatting) |
| FR-02.4 | Extraction agent shall retry with a tighter prompt if the Critic flags inadequate confidence (max 1 retry per fact type) |
| FR-02.5 | Every fact row shall include `source_chunk_id` linking back to the Qdrant chunk it was extracted from |
| FR-02.6 | Extraction shall write to PostgreSQL within the same evaluation run — no batch-delay |

## FR-03: Retrieval

| ID | Requirement |
|---|---|
| FR-03.1 | System shall perform hybrid search: dense cosine similarity + sparse BM25, fused via Reciprocal Rank Fusion (k=60) |
| FR-03.2 | System shall apply HyDE (hypothetical document embedding) before retrieval when enabled in org settings |
| FR-03.3 | System shall rewrite queries to formal procurement language before embedding when query rewriting is enabled |
| FR-03.4 | System shall rerank top-20 candidates to top-5 using configured reranker (BGE, Cohere, or ColBERT) |
| FR-03.5 | Retrieval Critic shall verify retrieved chunks are adequate for the criterion before passing to Extraction |
| FR-03.6 | All retrieval queries shall include org_id + vendor_id filters — no unfiltered collection scans |

## FR-04: Evaluation & Scoring

| ID | Requirement |
|---|---|
| FR-04.1 | Evaluation agent shall read facts from PostgreSQL — not from Qdrant chunks directly |
| FR-04.2 | Scoring rubric (criteria, weights, thresholds) shall be loaded from config — no hardcoded values in agent code |
| FR-04.3 | Each criterion score shall include a confidence score (0.0–1.0) and the evidence citations used |
| FR-04.4 | System shall retry evaluation if confidence is below `confidence_retry_threshold` (default 0.75) |
| FR-04.5 | Score bands (strongly_recommended / recommended / acceptable / marginal) shall be config-driven |

## FR-05: Comparison & Decision

| ID | Requirement |
|---|---|
| FR-05.1 | Comparator agent shall rank all vendors in a single RFP run using a SQL join across PostgreSQL fact tables |
| FR-05.2 | Comparator shall flag if rank margin between top-2 vendors is within `rank_margin_threshold` (default 3 points) |
| FR-05.3 | Decision agent shall route to approval tier based on contract value: <$100K → Dept Head, $100K–$500K → Regional Dir, >$500K → CFO |
| FR-05.4 | Approval tier thresholds shall be configurable per org in org_settings — not hardcoded |
| FR-05.5 | Decision agent shall create a pending approval record and notify the correct approver |

## FR-06: Explanation & Reporting

| ID | Requirement |
|---|---|
| FR-06.1 | Explanation agent shall generate a structured report where every claim is cited to a verbatim source quote |
| FR-06.2 | Report shall include: executive summary, per-vendor scores, comparison table, risk flags, recommended vendor |
| FR-06.3 | System shall export report as PDF, accessible from the dashboard immediately after evaluation completes |
| FR-06.4 | Report citation style (inline / footnote) shall be configurable per org |

## FR-07: Critic Agent (Cross-Cutting)

| ID | Requirement |
|---|---|
| FR-07.1 | Critic agent shall run after every agent in the pipeline — it cannot be skipped |
| FR-07.2 | HARD flags shall block the pipeline and escalate to the Procurement Manager |
| FR-07.3 | SOFT flags shall log a warning but allow the pipeline to continue |
| FR-07.4 | Every Critic run shall be logged to the observability provider with agent name, flag type, and reason |
| FR-07.5 | Critic shall verify: grounding quote present and non-empty, confidence above floor, no cross-tenant references |

## FR-08: CEO Dashboard

| ID | Requirement |
|---|---|
| FR-08.1 | Dashboard shall display: active RFPs, completed evaluations, pending approvals, committed spend — filterable by department and region |
| FR-08.2 | Dashboard shall show total committed vendor spend, updated in real time when a vendor decision is recorded |
| FR-08.3 | Dashboard shall fire a duplicate vendor alert when the same vendor appears in 2+ active evaluations across departments |
| FR-08.4 | Dashboard shall fire a pricing anomaly alert when the same vendor's contract value differs >15% across regions |
| FR-08.5 | CEO can drill down from any summary metric to the underlying evaluation report in one click |
| FR-08.6 | Dashboard data shall refresh within 30 seconds of any pipeline event |

## FR-09: Multi-Tenancy & Access Control

| ID | Requirement |
|---|---|
| FR-09.1 | Every API request shall include a valid JWT token; unauthenticated requests return 401 |
| FR-09.2 | org_id shall be extracted from the JWT and applied to every database query — no org_id override via request body |
| FR-09.3 | CEO and CFO roles shall see all departments and regions within their organisation |
| FR-09.4 | Department Head role shall see only evaluations tagged with their department_id |
| FR-09.5 | Regional Director role shall see only evaluations tagged with their region_id |
| FR-09.6 | Vendor data uploaded by Org A shall never be accessible to Org B under any condition |

## FR-10: Audit & Override

| ID | Requirement |
|---|---|
| FR-10.1 | Human overrides shall create an AuditOverride record: timestamp, user_id, original value, new value, justification |
| FR-10.2 | Justification field is mandatory for all overrides — system shall reject override requests with empty justification |
| FR-10.3 | Audit records shall be immutable — no UPDATE or DELETE permitted on audit tables |
| FR-10.4 | Audit log shall be exportable as CSV or JSON for external auditor access |
| FR-10.5 | All audit records shall be retained for the period defined in product.yaml (default 7 years) |

## FR-11: Configuration

| ID | Requirement |
|---|---|
| FR-11.1 | LLM provider shall be configurable via LLM_PROVIDER env var — no code changes required |
| FR-11.2 | Embedding provider shall be configurable via EMBEDDING_PROVIDER env var |
| FR-11.3 | Reranker shall be configurable via RERANKER_PROVIDER env var |
| FR-11.4 | Observability provider shall be configurable via OBSERVABILITY_PROVIDER env var |
| FR-11.5 | Per-org settings (quality tier, output tone, language, citation style) shall be stored in org_settings table and overridable via admin API |
| FR-11.6 | New orgs shall inherit defaults from product.yaml new_org_defaults — no manual setup required |
