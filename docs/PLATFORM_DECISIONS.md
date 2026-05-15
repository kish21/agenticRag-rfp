# Platform Decisions & Implementation Log
*Last updated: 2026-05-14*

---

## What This Platform Is

**Enterprise Agentic AI Platform** — starting with an RFP Evaluation Agent.
Multi-tenant SaaS. 9-agent pipeline with structured outputs, critic guardrails, and full audit trail.
Designed for enterprise procurement teams (NHS, councils, FTSE 100, consulting firms).

---

## The 9 Agents

| # | Agent | Role | LLM? | Key Output |
|---|---|---|---|---|
| 1 | Planner | Builds typed task DAG | No — deterministic | `PlannerOutput` |
| 2 | Ingestion | Chunk + embed documents → Qdrant | No — pipeline | `IngestionOutput` |
| 3 | Retrieval | Hybrid search + rerank | Yes — query rewriting, HyDE | `RetrievalOutput` |
| 4 | Extraction | Structured facts → PostgreSQL | Yes — JSON extraction | `ExtractionOutput` |
| 5 | Evaluation | Score vendors against criteria | Yes — rubric scoring | `EvaluationOutput` |
| 6 | Comparator | Cross-vendor ranking | Yes — differentiators | `ComparatorOutput` |
| 7 | Decision | Governance routing + approval tiers | Yes — fallback only | `DecisionOutput` |
| 8 | Explanation | Grounded report, every claim cited | Yes — narrative | `ExplanationOutput` |
| 9 | Critic | Validates every agent output | No — rule-based | `CriticOutput` |

Every agent output is a Pydantic model. Every extracted fact has a `grounding_quote`.
Critic runs after every agent — cannot be skipped. HARD flag blocks the pipeline.

---

## Tech Stack — Finalised

### Storage
| Layer | Technology | Why |
|---|---|---|
| Vector store | Qdrant (local Docker) | Dense + sparse vectors, org-level tenant isolation |
| Structured facts | PostgreSQL (local Docker) | Typed SQL comparisons, Row-Level Security |
| Both required | — | Evaluation reads PostgreSQL facts, NOT Qdrant chunks |

### Retrieval Pipeline
| Component | Technology | Notes |
|---|---|---|
| Chunking | LlamaIndex HierarchicalNodeParser + SentenceWindowNodeParser | 3 levels: summary/detail/leaf |
| Dense embeddings | **Configurable** (see Embedding Provider below) | Default: OpenAI 3072-dim |
| Sparse embeddings | BM25 TF-IDF approximation | 100K hash bins, in-process |
| Hybrid fusion | Reciprocal Rank Fusion (RRF) in Qdrant | k=60 |
| Reranking | **BGE cross-encoder** `BAAI/bge-reranker-v2-m3` | Local, no API cost |
| HyDE | LLM generates hypothetical doc, embeds that | Enabled for all tiers |
| Query rewriting | LLM rewrites to formal procurement language | Enabled for all tiers |

### Observability
| Tool | Role | Status |
|---|---|---|
| LangSmith | Passive tracing via env vars | Active |
| LangFuse | Agent run + critic flag logging | Active (swappable — see below) |

### Infrastructure
| Component | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Orchestration | LangGraph |
| Burst compute | Modal (serverless GPU/CPU) |
| Monitoring | LangSmith + LangFuse |
| Auth | JWT |
| Frontend | Next.js |

---

## Provider Abstractions Built

All providers follow the same pattern as `llm_provider.py` — swap via `.env`, zero code changes.

### LLM Provider (`app/core/llm_provider.py`)
```
LLM_PROVIDER=openai       → GPT-4o (current default)
LLM_PROVIDER=anthropic    → Claude (key not configured yet)
LLM_PROVIDER=openrouter   → Any model via OpenRouter API
LLM_PROVIDER=ollama       → Local models (Qwen, Llama, Mistral)
LLM_PROVIDER=azure        → Azure OpenAI
LLM_PROVIDER=modal        → Qwen 2.5 72B AWQ via vLLM on Modal A100 (open source, no per-token cost)
```

### Embedding Provider (`app/core/embedding_provider.py`) ← NEW
```
EMBEDDING_PROVIDER=openai   → text-embedding-3-large, 3072-dim (current default)
EMBEDDING_PROVIDER=azure    → Azure OpenAI embedding deployment
EMBEDDING_PROVIDER=local    → BAAI/bge-large-en-v1.5, 1024-dim (CPU, sentence-transformers)
EMBEDDING_PROVIDER=modal    → BAAI/bge-large-en-v1.5, 1024-dim (Modal A10G GPU, batch)
```
Switching model changes vector dimensions. Existing Qdrant collections need re-ingestion.

### Reranker Provider (`app/core/reranker_provider.py`)
```
RERANKER_PROVIDER=bge     → BAAI/bge-reranker-v2-m3, local CrossEncoder (current default)
RERANKER_PROVIDER=cohere  → Cohere Rerank v3 API (paid)
RERANKER_PROVIDER=colbert → ColBERT v2.0 via ragatouille (local)
RERANKER_PROVIDER=none    → Vector score order, no reranking
```

### Observability Provider (`app/core/observability_provider.py`) ← NEW
```
OBSERVABILITY_PROVIDER=langfuse  → LangFuse cloud (current default)
OBSERVABILITY_PROVIDER=stdout    → JSON logs to console (dev/air-gapped)
OBSERVABILITY_PROVIDER=none      → Silent drop (testing/CI)
```

### Compute Provider — PLANNED (not built yet)
```
COMPUTE_PROVIDER=modal           → Modal serverless (current, hardwired)
COMPUTE_PROVIDER=azure_functions → Azure Functions HTTP trigger
COMPUTE_PROVIDER=aws_lambda      → AWS Lambda invoke
COMPUTE_PROVIDER=local_worker    → In-process FastAPI (air-gapped)
```

---

## Modal Deployment

### Images & Functions

| Image | Packages | Functions | GPU |
|---|---|---|---|
| `pdf_image` | pypdf, llama-index, openai, sqlalchemy | `extract_pdf_on_modal` | CPU |
| `embed_image` | sentence-transformers, torch | `embed_batch_on_modal`, `embed_single_on_modal` | A10G |
| `llm_image` | nvidia/cuda:12.4.0 + vLLM==0.5.3 | `serve_llm_on_modal`, `download_llm_weights` | A100-80GB |

### Deploy command
```bash
modal deploy app_modal.py --env rag
```

### After deploy — configure .env
```
LLM_PROVIDER=modal
MODAL_LLM_ENDPOINT=https://<workspace>--agentic-platform-serve-llm-on-modal.modal.run
MODAL_LLM_MODEL=qwen2.5-72b
```

### One-time model weight pre-download
```bash
modal run app_modal.py::download_llm_weights --env rag
```
Caches Qwen 2.5 72B AWQ weights in a Modal Volume (`agentic-llm-weights`) so cold starts don't re-download 36GB.

### Why batch embedding on Modal GPU
During ingestion, a 50-page PDF produces ~200 chunks. Each needs an embedding vector.
- OpenAI API: 200 sequential calls → slow + paid per token
- Modal A10G: 200 chunks in one batch call → ~200ms on GPU, no per-token cost

---

## LLM — Decision: Modal vLLM (NOT Ollama locally)

**Reason:** Local desktop has insufficient RAM for 72B model. Ollama locally is not viable.

**Decision: Run Qwen 2.5 72B on Modal A100 via vLLM.**

**Why this is better than OpenRouter long-term:**
- Same Modal infrastructure used for both inference AND fine-tuning
- When a procurement-specific or HR-specific fine-tuned model is ready, swap model path — nothing else changes
- Fully open source, no per-token API cost at scale
- One GPU platform (Modal) for all heavy compute

**Planned Modal LLM function:**
```python
llm_image = Image.debian_slim().pip_install("vllm==0.4.3")

@app.function(gpu="A100", image=llm_image, min_containers=1, timeout=600)
@modal.wsgi_app()
def serve_llm_on_modal():
    # Exposes OpenAI-compatible /v1/chat/completions endpoint
    # LLM_PROVIDER=openai + OPENAI_BASE_URL=<modal endpoint>
```

**Fine-tuning path (same infrastructure):**
- Procurement domain: fine-tune on RFP/proposal text pairs
- HR domain: fine-tune on HR policy question-answer pairs
- Legal domain: fine-tune on contract clause pairs
- Training job runs on Modal H100, outputs saved to Modal Volume
- Inference function loads fine-tuned weights from Volume

**Not built yet** — requires cloud PostgreSQL first (Modal cannot reach localhost).

---

## Quality Tiers — Unified

All three tiers (fast/balanced/accurate) are now identical. Differentiation to be added
when real customer usage data informs the right trade-offs.

| Setting | Value (all tiers) |
|---|---|
| HyDE | On |
| Hybrid search | On |
| Query rewriting | On |
| Reranking | On (BGE) |
| retrieval_top_k | 10 |
| rerank_top_n | 5 |
| confidence_retry_threshold | 0.75 |
| llm_temperature | 0.1 |

---

## Enterprise Deployment Profiles

Customers install with a `.env` file — no code changes.

| Profile | LLM | Embeddings | Reranker | Compute |
|---|---|---|---|---|
| **Demo / small** | Modal vLLM (Qwen) | Modal BGE | BGE local | Modal |
| **Azure enterprise** | Azure OpenAI | Azure OpenAI | BGE local | Azure Functions |
| **AWS enterprise** | OpenAI / Bedrock | Local BGE | BGE local | AWS Lambda |
| **Air-gapped / on-prem** | Modal vLLM or Ollama | Local BGE | BGE local | local_worker |

---

## Paid vs Open Source — Current State

| Component | Was | Now | Remaining cost |
|---|---|---|---|
| LLM | OpenAI GPT-4o | → Modal vLLM Qwen 2.5 72B (planned) | Modal GPU time only |
| Embeddings | OpenAI API | → Modal BGE (when EMBEDDING_PROVIDER=modal) | Modal GPU time only |
| Reranker | Cohere Rerank v3 | → BGE CrossEncoder (done) | Free |
| Observability | LangFuse (cloud) | → Swappable (done) | Free if self-hosted |
| LangSmith | Paid at scale | Kept (passive tracing) | Paid |
| Vector DB | — | Qdrant local Docker | Free |
| Relational DB | — | PostgreSQL local Docker | Free |
| Burst compute | — | Modal | Pay per use |

---

## Data Cleanup

All data was dummy. Reset script:
```bash
python scripts/reset_dev_data.py
```
Truncates all PostgreSQL fact/run tables, deletes all Qdrant collections, re-seeds criteria templates.

---

## Agent Improvements — Backlog

### Tier 1 — Do Next (high value, low risk)
| Agent | Improvement |
|---|---|
| Ingestion | Table-aware PDF parsing (pdfplumber/pymupdf4llm) — biggest source of extraction failures |
| Extraction | Structured output via `tool_use` API — eliminates JSON parsing fragility |
| Decision | Configurable approval tiers per org/dept (move hardcoded $100K/$500K to `org_settings`) |
| Explanation | Citation footnotes with page numbers in PDF report |

### Tier 2 — After First Customer
| Agent | Improvement |
|---|---|
| Retrieval | Query decomposition for multi-part criteria |
| Retrieval | Adaptive K selection based on rerank score spread |
| Evaluation | Comparative rubric scoring (cross-vendor normalisation) |
| Evaluation | Bayesian confidence intervals on scores |
| Comparator | Monte Carlo rank stability simulation |
| Critic | Flag learning from human overrides |

### Tier 3 — Backlog (customer-driven)
| Agent | Improvement |
|---|---|
| Planner | Parallel task scheduling |
| Ingestion | Domain-specific embedding fine-tuning (procurement/HR/legal) |
| Retrieval | RAPTOR recursive retrieval |
| Explanation | Multilingual output |
| Critic | ISO 42001 AI governance clause mapping |
| Decision | Conflict of interest detection (needs HR/ERP integration) |

---

## What's Next (Priority Order)

1. **`modal deploy app_modal.py --env rag`** — deploy all three images (off VPN; SSL issue blocks gRPC)
2. **`modal run app_modal.py::download_llm_weights --env rag`** — pre-cache model weights in Volume
3. **Set `MODAL_LLM_ENDPOINT` in `.env`** after deploy, switch `LLM_PROVIDER=modal`
4. **`compute_provider.py`** — abstraction layer so Azure/AWS customers don't need Modal
5. **Tier 1 agent improvements** — table-aware PDF, tool_use extraction, configurable tiers
6. **Cloud PostgreSQL** — unblocks `daily_cleanup` and `rate_monitor` on Modal
7. **SOC 2 / ISO 27001** — required for enterprise procurement sign-off

---

## Files Changed This Session

| File | Change |
|---|---|
| `scripts/reset_dev_data.py` | New — wipe PostgreSQL + Qdrant + re-seed |
| `.env` | BGE reranker, embedding/observability providers, Modal LLM endpoint |
| `app/config/product.yaml` | All three tiers unified, hybrid on, BGE |
| `app/config/platform.yaml` | New `embedding:` section with model→dimensions map |
| `app/config/loader.py` | `PlatformEmbedding` model, new Settings fields incl. modal_llm_endpoint/model |
| `app/core/embedding_provider.py` | New — openai/azure/local/modal backends |
| `app/core/observability_provider.py` | New — langfuse/stdout/none backends |
| `app/core/langfuse_client.py` | Deleted — replaced by observability_provider.py |
| `app/core/llamaindex_pipeline.py` | Removed hardwired OpenAI client, batch embedding |
| `app/core/llm_provider.py` | Added `modal` provider (AsyncOpenAI → Modal vLLM endpoint) |
| `app/core/qdrant_client.py` | Config-driven dimensions, embed_text() for hybrid search |
| `app/jobs/rate_monitor.py` | Import updated to observability_provider |
| `app/jobs/cleanup.py` | Import updated to observability_provider |
| `app_modal.py` | Added embed_image, llm_image, serve_llm_on_modal, download_llm_weights |
