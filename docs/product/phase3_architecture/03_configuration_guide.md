# Configuration Guide — Customer & Platform Settings
*Version 1.0 — 2026-05-14*

---

## How Configuration Works

This platform has three levels of configuration:

```
Level 1: .env file           — Provider selection, credentials, infrastructure URLs
Level 2: YAML config files   — Platform behaviour, agent thresholds, LLM models
Level 3: org_settings table  — Per-organisation overrides (runtime, via admin API)
```

Customers configure Level 1 only (`.env`). Product engineers configure Level 2. Customer admins configure Level 3 via the admin UI.

**Zero code changes are required to switch any provider or adjust any threshold.**

---

## Level 1 — .env Configuration (Customer-Facing)

### LLM Provider

```env
# Choose one:
LLM_PROVIDER=openai        # GPT-4o — default, best quality
LLM_PROVIDER=anthropic     # Claude via Anthropic SDK
LLM_PROVIDER=openrouter    # Any model via OpenRouter (200+ models)
LLM_PROVIDER=ollama        # Local models (Qwen 2.5, Llama 3, Mistral)
LLM_PROVIDER=azure         # Azure OpenAI (enterprise, in-region)
LLM_PROVIDER=modal         # Qwen 2.5 72B AWQ via vLLM — no per-token cost
```

| Provider | Required Keys | Model Used |
|---|---|---|
| openai | `OPENAI_API_KEY` | `OPENAI_MODEL=gpt-4o` |
| anthropic | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL=claude-opus-4-7` |
| openrouter | `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` | `OPENROUTER_MODEL=<any>` |
| ollama | None (local) | `OLLAMA_MODEL=qwen2.5:72b`, `OLLAMA_BASE_URL=http://localhost:11434` |
| azure | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION` | `AZURE_OPENAI_DEPLOYMENT=<deployment-name>` |
| modal | `MODAL_LLM_ENDPOINT` (URL after modal deploy) | `MODAL_LLM_MODEL=qwen2.5-72b` |

### Embedding Provider

```env
# Choose one:
EMBEDDING_PROVIDER=openai   # text-embedding-3-large, 3072-dim — default
EMBEDDING_PROVIDER=azure    # Azure OpenAI embedding deployment
EMBEDDING_PROVIDER=local    # BAAI/bge-large-en-v1.5, 1024-dim (CPU, free)
EMBEDDING_PROVIDER=modal    # BAAI/bge-large-en-v1.5, 1024-dim (A10G GPU, batch, fast)
```

**Important:** Switching embedding provider changes vector dimensions. Existing Qdrant collections must be re-ingested with the new model. Run `python scripts/reset_dev_data.py` before re-ingesting in dev.

### Reranker Provider

```env
# Choose one:
RERANKER_PROVIDER=bge       # BAAI/bge-reranker-v2-m3, local CrossEncoder — default, free
RERANKER_PROVIDER=cohere    # Cohere Rerank v3 API — paid, highest quality
RERANKER_PROVIDER=colbert   # ColBERT v2.0, local — token-level late interaction
RERANKER_PROVIDER=none      # No reranking — vector score order only (dev/testing)
```

### Observability Provider

```env
# Choose one:
OBSERVABILITY_PROVIDER=langfuse   # LangFuse cloud — default, agent run logging
OBSERVABILITY_PROVIDER=stdout     # JSON logs to console (dev / air-gapped)
OBSERVABILITY_PROVIDER=none       # Silent drop (testing / CI)
```

LangSmith tracing is always active when `LANGCHAIN_API_KEY` is set — it is passive (env var only).

### Infrastructure

```env
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/rfp_eval

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=                    # Leave empty for local Docker

# Security
JWT_SECRET_KEY=<random 32+ char string>
SSL_VERIFY=true                    # Set to false only for corporate proxy dev environments

# LangSmith (optional but recommended)
LANGCHAIN_API_KEY=<key>
LANGCHAIN_PROJECT=rfp-eval-prod
LANGCHAIN_TRACING_V2=true

# LangFuse (if OBSERVABILITY_PROVIDER=langfuse)
LANGFUSE_SECRET_KEY=<key>
LANGFUSE_PUBLIC_KEY=<key>
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## Level 2 — YAML Configuration (Platform / Product)

### app/config/product.yaml — Agent Behaviour

```yaml
# Defaults for new organisations (before any admin customisation)
new_org_defaults:
  quality_tier: balanced          # fast | balanced | accurate
  output_tone: formal             # formal | analytical | summary
  output_language: en-GB          # BCP 47 language tag
  citation_style: inline          # inline | footnote
  include_confidence_score: true
  include_evidence_quotes: true
  max_evidence_quote_chars: 300   # Max length of grounding quote in report
  score_variance_threshold: 0.15  # Flag if variance across criteria < this
  rank_margin_threshold: 3        # Flag if top-2 vendors within this many points
  parallel_vendors: true          # Evaluate multiple vendors concurrently

# Quality tier presets
presets:
  fast | balanced | accurate:
    use_hyde: true
    use_reranking: true
    use_query_rewriting: true
    use_hybrid_search: true
    reranker_provider: "bge"
    retrieval_top_k: 10
    rerank_top_n: 5
    mandatory_check_use_llm_verify: true
    confidence_retry_threshold: 0.75
    llm_temperature: 0.1

# Score → recommendation band
score_bands:
  strongly_recommended: 85        # Score >= 85
  recommended: 70                 # Score >= 70
  acceptable: 50                  # Score >= 50
  marginal: 0                     # Score >= 0

# Audit retention
audit:
  retain_decisions_years: 7       # Minimum 7 — cannot be lowered below 7
  require_human_signoff: true
  citation_required: true
```

### app/config/platform.yaml — Infrastructure Parameters

```yaml
ingestion:
  chunk_size_tokens: 500          # Characters per chunk
  chunk_overlap_tokens: 50        # Overlap between adjacent chunks
  max_chunk_chars_for_rerank: 512 # Truncate chunk before feeding to reranker

embedding:
  openai_model: "text-embedding-3-large"
  local_model: "BAAI/bge-large-en-v1.5"
  dimensions:
    text-embedding-3-large: 3072
    BAAI/bge-large-en-v1.5: 1024
    nomic-ai/nomic-embed-text-v1.5: 768

retrieval:
  candidate_count_before_rerank: 20
  reranker_models:
    cohere: "rerank-english-v3.0"
    bge: "BAAI/bge-reranker-v2-m3"
    colbert: "colbert-ir/colbertv2.0"
  fusion_method: "rrf"
  rrf_k: 60

llm:
  primary_model: "gpt-4o"
  fallback_model: "gpt-4o-mini"
  max_tokens: 4096
  request_timeout_seconds: 120

infrastructure:
  org_settings_cache_ttl_seconds: 60   # Cache per-org settings for 60s
  max_retries: 5                        # LLM rate limit retries
  qdrant_collection_pattern: "{org_id}__{vendor_id}"
  retrieval_critic_max_retries: 1
  retrieval_critic_confidence_floor: 0.6
  extraction_critic_max_retries: 1
  extraction_critic_confidence_floor: 0.7
```

---

## Level 3 — Per-Organisation Settings (Admin API)

These settings are stored in the `org_settings` PostgreSQL table and override product.yaml defaults per organisation. They are changed via the admin API — no YAML edits required.

### Configurable Per-Org Settings

| Setting | Type | Default | Description |
|---|---|---|---|
| `quality_tier` | string | balanced | Retrieval + scoring profile |
| `use_hyde` | bool | true | Enable HyDE query expansion |
| `use_reranking` | bool | true | Enable reranker |
| `use_query_rewriting` | bool | true | LLM query rewrite before embedding |
| `use_hybrid_search` | bool | true | Dense + sparse fusion |
| `reranker_provider` | string | bge | Override reranker per org |
| `retrieval_top_k` | int | 10 | Chunks retrieved before rerank |
| `rerank_top_n` | int | 5 | Chunks after reranking |
| `confidence_retry_threshold` | float | 0.75 | Retry if below this |
| `llm_temperature` | float | 0.1 | LLM temperature for this org |
| `output_tone` | string | formal | Report tone |
| `output_language` | string | en-GB | Report language |
| `citation_style` | string | inline | inline \| footnote |
| `include_confidence_score` | bool | true | Show confidence in report |
| `include_evidence_quotes` | bool | true | Show grounding quotes in report |
| `max_evidence_quote_chars` | int | 300 | Max grounding quote length |
| `parallel_vendors` | bool | true | Evaluate vendors in parallel |

### Admin API Endpoints

```
GET  /admin/orgs/{org_id}/settings          — view current org settings
PUT  /admin/orgs/{org_id}/settings          — update settings (audited)
POST /admin/orgs                            — create new org (inherits defaults)
GET  /admin/orgs/{org_id}/settings/audit    — view settings change history
```

All setting changes are written to `org_settings_audit` — immutable change log with `changed_by`, `field_name`, `old_value`, `new_value`, timestamp.

---

## Enterprise Deployment Profiles

Configure everything via `.env` — no code changes required.

### Profile A — Demo / Small Team
```env
LLM_PROVIDER=modal
EMBEDDING_PROVIDER=modal
RERANKER_PROVIDER=bge
OBSERVABILITY_PROVIDER=langfuse
```
Cost: Modal GPU time only. No per-token API cost.

### Profile B — Azure Enterprise
```env
LLM_PROVIDER=azure
EMBEDDING_PROVIDER=azure
RERANKER_PROVIDER=bge
OBSERVABILITY_PROVIDER=langfuse
```
Cost: Azure OpenAI consumption. Data stays in Azure region. No data leaves Microsoft infrastructure.

### Profile C — AWS Enterprise
```env
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=local
RERANKER_PROVIDER=bge
OBSERVABILITY_PROVIDER=stdout
```
Cost: OpenAI API. Embedding and reranking are free (local). Logs go to CloudWatch via stdout.

### Profile D — Air-Gapped / On-Premises (NHS, Government)
```env
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=local
RERANKER_PROVIDER=bge
OBSERVABILITY_PROVIDER=stdout
SSL_VERIFY=false
```
Cost: Zero API cost. All compute runs locally. No internet access required after initial model download.

---

## How to Change a Setting

### Change LLM provider (example: switch from OpenAI to Azure)
1. Update `.env`: `LLM_PROVIDER=azure`, add `AZURE_OPENAI_*` keys
2. Restart FastAPI: `uvicorn app.main:app --reload`
3. No code changes. No database migration. No agent file edits.

### Change quality tier for one org
```bash
curl -X PUT /admin/orgs/my-org-id/settings \
  -H "Authorization: Bearer <admin-token>" \
  -d '{"quality_tier": "accurate", "reranker_provider": "cohere"}'
```
Change is live within 60 seconds (org_settings cache TTL).

### Add a new department as a new tenant
```bash
curl -X POST /admin/orgs \
  -H "Authorization: Bearer <admin-token>" \
  -d '{"org_id": "nhs-trust-north", "org_name": "NHS Trust North", "region": "UK-North"}'
```
New org inherits all `new_org_defaults` from product.yaml. No manual database setup.
