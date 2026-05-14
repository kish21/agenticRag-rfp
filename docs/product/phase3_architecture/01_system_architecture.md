# System Architecture Document
*Version 1.0 — 2026-05-14*

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CUSTOMER SURFACES                            │
│                                                                     │
│  CEO Dashboard (Next.js)   Procurement UI   Admin Console           │
│  ─ Global spend view       ─ Upload PDFs    ─ Tenant mgmt           │
│  ─ Duplicate alerts        ─ Review facts   ─ RBAC config           │
│  ─ Pricing anomalies       ─ Override       ─ API key rotation      │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ HTTPS / JWT
┌─────────────────────▼───────────────────────────────────────────────┐
│                     FastAPI (app/main.py)                           │
│  ─ JWT auth (app/core/auth.py)                                      │
│  ─ org_id injection from token                                      │
│  ─ Routes: /api/* (app/api/routes.py)                               │
│  ─ Admin routes: /admin/* (app/api/admin_routes.py)                 │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────────┐
│                  LangGraph Pipeline (9 Agents)                      │
│                                                                     │
│  [1] Planner ──► [2] Ingestion ──► [3] Retrieval                   │
│       │                                  │                          │
│       ▼                                  ▼                          │
│  [9] Critic ◄───────────────────── [4] Extraction                  │
│       │                                  │                          │
│       ▼                                  ▼                          │
│  [5] Evaluation ──► [6] Comparator ──► [7] Decision                │
│                                          │                          │
│                                          ▼                          │
│                                    [8] Explanation                  │
│                                          │                          │
│                              [9] Critic (after each)               │
└────────────┬──────────────────────────┬──────────────────────────────┘
             │                          │
┌────────────▼────────┐    ┌────────────▼────────────────────────────┐
│  Qdrant (vectors)   │    │  PostgreSQL (structured facts)          │
│  ─ Dense embeddings │    │  ─ extracted_certifications             │
│  ─ Sparse BM25      │    │  ─ extracted_insurance                  │
│  ─ org_id filtered  │    │  ─ extracted_slas, pricing, projects    │
│  ─ vendor_id scoped │    │  ─ evaluation_runs, scores, decisions   │
└─────────────────────┘    │  ─ audit_overrides (insert-only)        │
                           │  ─ org_settings + audit                 │
                           └─────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────────────────┐
│                    Modal (Serverless GPU/CPU)                       │
│  ─ PDF extraction: extract_pdf_on_modal (CPU burst)                │
│  ─ Batch embedding: embed_batch_on_modal (A10G GPU)                │
│  ─ LLM inference: serve_llm_on_modal (A100-80GB, Qwen 2.5 72B)    │
└─────────────────────────────────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────────────────┐
│                    Observability                                    │
│  ─ LangSmith: passive LLM call tracing (env var activation)        │
│  ─ LangFuse: agent run logging, Critic flag logging                │
│  ─ Rate monitor job: runs every 30 min (app/jobs/rate_monitor.py)  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. The 9 Agents

| # | Agent | File | Input | Output Model | LLM? |
|---|---|---|---|---|---|
| 1 | Planner | `app/agents/planner.py` | RFP criteria, vendor list | `PlannerOutput` | No — deterministic |
| 2 | Ingestion | `app/agents/ingestion.py` | PDF file path, org_id, vendor_id | `IngestionOutput` | No — pipeline |
| 3 | Retrieval | `app/agents/retrieval.py` | Criteria, org_id, vendor_id | `RetrievalOutput` | Yes — HyDE + query rewrite |
| 4 | Extraction | `app/agents/extraction.py` | Retrieved chunks, criterion | `ExtractionOutput` | Yes — JSON extraction |
| 5 | Evaluation | `app/agents/evaluation.py` | PostgreSQL facts, rubric | `EvaluationOutput` | Yes — rubric scoring |
| 6 | Comparator | `app/agents/comparator.py` | All vendor scores | `ComparatorOutput` | Yes — differentiators |
| 7 | Decision | `app/agents/decision.py` | Comparison, contract value | `DecisionOutput` | Yes — fallback only |
| 8 | Explanation | `app/agents/explanation.py` | All prior outputs | `ExplanationOutput` | Yes — narrative |
| 9 | Critic | `app/agents/critic.py` | Any agent output | `CriticOutput` | No — rule-based |

**Invariants:**
- Every agent output is a Pydantic model — never raw text
- Critic runs after every agent — topology enforced in LangGraph
- Every extracted fact has `grounding_quote` (verbatim from source)
- Every agent reads `org_id` — never cross-tenant

---

## 3. Data Flow

### Ingestion Flow
```
PDF upload → RFP identity confirmation → LlamaIndex chunker
  → HierarchicalNodeParser (summary/detail/leaf nodes)
  → SentenceWindowNodeParser (sentence-level context)
  → Embedding provider (dense: text-embedding-3-large or BGE)
  → BM25 sparse vectors (in-process, 100K hash bins)
  → Qdrant upsert (collection: {org_id}__{vendor_id})
  → Critic validation → IngestionOutput
```

### Retrieval Flow
```
Criterion text
  → Query rewriter (LLM → formal procurement language)
  → HyDE generator (LLM → hypothetical vendor response)
  → HyDE embedding (same model as ingestion)
  → Qdrant hybrid query (dense + sparse, RRF k=60)
  → Reranker (BGE CrossEncoder → top-5)
  → Retrieval Critic (adequacy check)
  → Retrieved chunks passed to Extraction
```

### Extraction Flow
```
Retrieved chunks + criterion
  → LLM (JSON extraction prompt)
  → Pydantic parse
  → Grounding check (verbatim quote in source text)
  → Whitespace normalisation (PDF table cell fix)
  → PostgreSQL INSERT (fact_store.py)
  → Extraction Critic → ExtractionOutput
```

### Evaluation → CEO Dashboard Flow
```
Extracted facts (PostgreSQL)
  → Evaluation agent (rubric scoring)
  → Comparator agent (SQL join, cross-vendor)
  → Decision agent (approval tier routing)
  → Explanation agent (cited report)
  → Report PDF generated
  → CEO dashboard updated (committed spend, vendor choice, duplicate alerts)
```

---

## 4. Multi-Tenancy Architecture

```
Request arrives with JWT
  │
  ▼
app/core/auth.py extracts org_id from token
  │
  ▼
org_id injected into every DB call via SQLAlchemy session
  │
  ├── PostgreSQL: SET LOCAL app.org_id = '{org_id}' (enables RLS)
  └── Qdrant: every query includes filter {"org_id": org_id}
```

**Two-layer isolation:**
- API layer: org_id from JWT, never from request body
- Database layer: PostgreSQL RLS policy + Qdrant mandatory filter

---

## 5. Configuration Architecture

```
.env
  LLM_PROVIDER, EMBEDDING_PROVIDER, RERANKER_PROVIDER, OBSERVABILITY_PROVIDER
  → Read by app/config/loader.py (Settings model)
  → Consumed by provider modules (llm_provider.py, embedding_provider.py, etc.)

app/config/product.yaml
  → Agent behaviour: scoring thresholds, quality tiers, score bands, audit retention
  → Per-org defaults: new_org_defaults, quality tier presets

app/config/platform.yaml
  → Infrastructure: chunk sizes, embedding dimensions, retrieval config, LLM model names
  → Critic prompts: retrieval_critic_prompt, extraction_critic_prompt
  → HyDE templates: vendor_response, rfp_requirement, policy_document

app/core/org_settings.py
  → Resolves per-org config at request time (DB row if exists, else product.yaml defaults)
  → TTL-cached (60 seconds, configurable in platform.yaml)
```

---

## 6. CEO Dashboard Architecture

### Data Sources

| Widget | Source | Refresh |
|---|---|---|
| Active RFPs count | `evaluation_runs` table (status=running) | Real-time |
| Completed evaluations | `evaluation_runs` table (status=complete) | Real-time |
| Pending approvals | `evaluation_decisions` table (approval_status=pending) | Real-time |
| Total committed spend | SUM of `evaluation_decisions.contract_value` WHERE approved | Real-time |
| Duplicate vendor alert | Cross-run vendor_id match within same org, status=running | Event-driven |
| Pricing anomaly alert | Cross-region contract_value comparison (same vendor_id, >15% delta) | Event-driven |
| Vendor concentration | vendor_id share of total committed spend | Computed on load |

### Access Control

| Role | Departments visible | Regions visible |
|---|---|---|
| CEO, CFO | All | All |
| Regional Director | All in their region | Their region |
| Department Head | Their department | Their region |
| Procurement Manager | Their department | Their region |

---

## 7. Provider Abstraction Architecture

All providers follow the same pattern — swap via `.env`, zero agent code changes.

```
app/core/llm_provider.py        ← LLM_PROVIDER
app/core/embedding_provider.py  ← EMBEDDING_PROVIDER
app/core/reranker_provider.py   ← RERANKER_PROVIDER
app/core/observability_provider.py ← OBSERVABILITY_PROVIDER
app/core/compute_provider.py    ← COMPUTE_PROVIDER (planned)
```

Each module exports a single function/class that agents call.
Agents never import provider SDKs directly.
