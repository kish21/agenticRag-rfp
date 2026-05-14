# Deployment Runbook
*Version 1.0 — 2026-05-14*

---

## Local Development Stack

### Prerequisites
- Docker Desktop running
- Python 3.11+
- Node.js 20+ (frontend)
- Modal CLI installed (`pip install modal`)

### Start Local Stack

```bash
# 1. Start Qdrant + PostgreSQL
docker-compose up -d

# 2. Run PostgreSQL migrations
python scripts/migrate.py

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set LLM_PROVIDER, API keys, DATABASE_URL

# 5. Start FastAPI
uvicorn app.main:app --reload --port 8000

# 6. Start Next.js frontend
cd frontend && npm install && npm run dev

# 7. Verify
python checkpoint_runner.py status
python contract_tests.py
```

### Reset Dev Data

```bash
python scripts/reset_dev_data.py
# Truncates all PostgreSQL fact/run tables
# Deletes all Qdrant collections
# Re-seeds criteria templates
```

---

## Modal Deployment (GPU / Burst Compute)

### Prerequisites
- Modal account and CLI authenticated: `modal token new`
- Off VPN (Modal gRPC blocked by corporate VPN)
- `.env` with valid API keys

### Deploy All Three Images

```bash
modal deploy app_modal.py --env rag
```

This deploys:
- `extract_pdf_on_modal` — CPU image for PDF extraction
- `embed_batch_on_modal` / `embed_single_on_modal` — A10G GPU for batch embedding
- `serve_llm_on_modal` — A100-80GB for Qwen 2.5 72B vLLM inference

### Pre-Download Model Weights (One-Time)

```bash
modal run app_modal.py::download_llm_weights --env rag
```

Downloads Qwen 2.5 72B AWQ weights (36GB) into Modal Volume `agentic-llm-weights`.
Only needed once — weights are cached. Do not re-run unless model changes.

### Configure .env After Deploy

```bash
# Modal prints the endpoint URL after deploy. Copy it:
LLM_PROVIDER=modal
MODAL_LLM_ENDPOINT=https://<workspace>--agentic-platform-serve-llm-on-modal.modal.run
MODAL_LLM_MODEL=qwen2.5-72b
```

### Verify Modal Deployment

```bash
modal logs --env rag
# Look for: "vLLM engine loaded" — confirms A100 is serving
```

---

## Cloud Production Deployment

### Infrastructure Required

| Component | Recommended | Alternative |
|---|---|---|
| Qdrant | Qdrant Cloud (managed) | Self-hosted on cloud VM |
| PostgreSQL | Supabase / RDS / Cloud SQL | Self-hosted |
| FastAPI | Cloud Run / ECS / Azure Container Apps | VM with uvicorn |
| Frontend | Vercel / Netlify | Same container as FastAPI |
| LLM | Modal (A100) | Azure OpenAI |
| Observability | LangFuse Cloud + LangSmith | Self-hosted LangFuse |

### Production .env (Azure Enterprise Profile)

```env
# LLM
LLM_PROVIDER=azure
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_DEPLOYMENT=gpt-4o

# Embeddings
EMBEDDING_PROVIDER=azure

# Reranker
RERANKER_PROVIDER=bge

# Storage
DATABASE_URL=postgresql://user:pass@<cloud-host>:5432/rfp_eval
QDRANT_URL=https://<cluster>.qdrant.io
QDRANT_API_KEY=<key>

# Auth
JWT_SECRET_KEY=<random 64 char>

# Observability
OBSERVABILITY_PROVIDER=langfuse
LANGFUSE_SECRET_KEY=<key>
LANGFUSE_PUBLIC_KEY=<key>
LANGCHAIN_API_KEY=<key>
LANGCHAIN_PROJECT=rfp-eval-prod
LANGCHAIN_TRACING_V2=true

SSL_VERIFY=true
```

### Database Migration (Production)

```bash
# Run on first deploy only
python scripts/migrate.py --env production

# Verify RLS policies are active
python scripts/verify_rls.py
```

### New Tenant Onboarding

```bash
curl -X POST https://<api-host>/admin/orgs \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "acme-corp",
    "org_name": "ACME Corporation",
    "region": "UK-South",
    "department": "IT"
  }'
```

Response: New org created with defaults from product.yaml. No further setup required.

### JWT Secret Rotation

```bash
# 1. Generate new secret
python -c "import secrets; print(secrets.token_hex(32))"

# 2. Update .env: JWT_SECRET_KEY=<new secret>

# 3. Rolling restart (existing tokens invalidated — users must re-login)
# Cloud Run: deploy new revision
# ECS: update task definition, drain old tasks
# VM: systemctl restart rfp-api
```

---

## Rollback Procedure

### FastAPI rollback
```bash
# Cloud Run
gcloud run services update-traffic rfp-api --to-revisions=<prev-revision>=100

# ECS
aws ecs update-service --cluster rfp --service rfp-api --task-definition rfp-api:<prev-version>
```

### Database rollback
```bash
# Only if migration added a new table (safe to drop)
python scripts/rollback_migration.py --version <prev-version>
# NOTE: Never rollback if migration added RLS policies — re-adding is safer than removing
```

### Modal rollback
```bash
modal deploy app_modal.py --env rag  # Redeploy previous commit
```

---

## Health Checks

```bash
# API health
curl https://<api-host>/health
# Expected: {"status": "ok", "qdrant": "ok", "postgres": "ok"}

# Run contract tests against production
CONTRACT_ENV=production python contract_tests.py

# Run drift detector
python drift_detector.py
```
