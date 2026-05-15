# Multi-Cloud Deployment Guide
*Version 1.0 — 2026-05-14*

---

## How Provider Switching Works

Every cloud provider is configured via `.env` only. No code changes. No agent file edits.

```
.env change → restart FastAPI → new provider active
```

The four abstractions that make this possible:

```
LLM_PROVIDER         → app/core/llm_provider.py
EMBEDDING_PROVIDER   → app/core/embedding_provider.py
RERANKER_PROVIDER    → app/core/reranker_provider.py
OBSERVABILITY_PROVIDER → app/core/observability_provider.py
```

Agents call `call_llm()`, `get_embeddings()`, `rerank()` — they never import provider SDKs directly.

---

## Deployment Profile Summary

| Profile | LLM | Embeddings | Reranker | Compute | Best For |
|---|---|---|---|---|---|
| **Modal** | Qwen 2.5 72B (A100) | BGE (A10G) | BGE local | Modal serverless | Demo, cost-optimised |
| **Azure** | Azure OpenAI GPT-4o | Azure OpenAI | BGE local | Azure Container Apps | Enterprise, EU data residency |
| **AWS** | OpenAI GPT-4o | Local BGE | BGE local | ECS Fargate | AWS-native teams |
| **Google Cloud** | Vertex AI Gemini 1.5 Pro | Vertex AI | BGE local | Cloud Run | GCP-native, multimodal |
| **Air-gapped** | Ollama (Qwen 7B/14B) | Local BGE | BGE local | Local workers | NHS, government, no internet |

---

## Profile 1 — Modal (Recommended for Cost)

### What it uses
- LLM: Qwen 2.5 72B AWQ via vLLM on Modal A100-80GB
- Embeddings: BAAI/bge-large-en-v1.5 on Modal A10G (batch)
- Reranker: BAAI/bge-reranker-v2-m3 local CrossEncoder
- API: FastAPI on any cloud or local
- Storage: Qdrant Cloud + Supabase PostgreSQL (or local Docker for dev)

### Step-by-Step Deploy

**Step 1: Authenticate Modal**
```bash
pip install modal
modal token new
# Opens browser — sign in with GitHub or Google
```

**Step 2: Deploy all Modal functions**
```bash
# Must be off VPN — Modal uses gRPC which corporate VPNs block
modal deploy app_modal.py --env rag
```

Output will print three endpoints:
```
extract_pdf_on_modal   → https://<workspace>--agentic-platform-extract-pdf.modal.run
embed_batch_on_modal   → https://<workspace>--agentic-platform-embed-batch.modal.run
serve_llm_on_modal     → https://<workspace>--agentic-platform-serve-llm.modal.run
```

**Step 3: Pre-download model weights (one-time, ~20 minutes)**
```bash
modal run app_modal.py::download_llm_weights --env rag
# Downloads Qwen 2.5 72B AWQ (36GB) to Modal Volume 'agentic-llm-weights'
# Only needed once — cached for future cold starts
```

**Step 4: Configure .env**
```env
LLM_PROVIDER=modal
MODAL_LLM_ENDPOINT=https://<workspace>--agentic-platform-serve-llm.modal.run
MODAL_LLM_MODEL=qwen2.5-72b

EMBEDDING_PROVIDER=modal
RERANKER_PROVIDER=bge
OBSERVABILITY_PROVIDER=langfuse

DATABASE_URL=postgresql://user:pass@<supabase-host>:5432/postgres
QDRANT_URL=https://<cluster>.qdrant.io
QDRANT_API_KEY=<key>
JWT_SECRET_KEY=<random-64-chars>
```

**Step 5: Start FastAPI**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Or deploy to any cloud — FastAPI is stateless, no cloud dependency
```

**Step 6: Verify**
```bash
curl http://localhost:8000/health
# {"status":"ok","qdrant":"ok","postgres":"ok"}

python contract_tests.py
python checkpoint_runner.py status
```

**Step 7: Test LLM (confirm Modal A100 is serving)**
```bash
python scripts/test_llm_call.py
# First call: 5–10 min cold start (A100 spinning up + vLLM loading model)
# Subsequent calls: <15 seconds
```

### Cost at this profile
- Modal A100 LLM: ~$3–4/GPU-hour (pay per use, no idle cost)
- Modal A10G embedding: ~$0.50/GPU-hour
- Qdrant Cloud Starter: $25/month
- Supabase Pro: $25/month
- **Total: ~$50–200/month** depending on evaluation volume

---

## Profile 2 — Microsoft Azure

### What it uses
- LLM: Azure OpenAI GPT-4o (in-region, no data leaves Azure)
- Embeddings: Azure OpenAI text-embedding-3-large (in-region)
- Reranker: BAAI/bge-reranker-v2-m3 (local, runs in container)
- API: Azure Container Apps (auto-scaling)
- Storage: Azure Database for PostgreSQL + Qdrant Cloud (or Azure VM with Qdrant)
- Observability: LangFuse Cloud or self-hosted on Azure

### Prerequisites
- Azure subscription with Azure OpenAI access approved (requires Microsoft approval)
- Azure CLI installed: `az login`
- Azure OpenAI resource created with GPT-4o and text-embedding-3-large deployments

### Step-by-Step Deploy

**Step 1: Create Azure OpenAI resource**
```bash
az group create --name rfp-eval-rg --location uksouth
az cognitiveservices account create \
  --name rfp-openai \
  --resource-group rfp-eval-rg \
  --kind OpenAI \
  --sku S0 \
  --location uksouth

# Deploy GPT-4o
az cognitiveservices account deployment create \
  --name rfp-openai \
  --resource-group rfp-eval-rg \
  --deployment-name gpt-4o \
  --model-name gpt-4o \
  --model-version "2024-05-13" \
  --model-format OpenAI \
  --sku-capacity 100 \
  --sku-name Standard

# Deploy embedding model
az cognitiveservices account deployment create \
  --name rfp-openai \
  --resource-group rfp-eval-rg \
  --deployment-name text-embedding-3-large \
  --model-name text-embedding-3-large \
  --model-version "1" \
  --model-format OpenAI \
  --sku-capacity 100 \
  --sku-name Standard

# Get endpoint and key
az cognitiveservices account show --name rfp-openai --resource-group rfp-eval-rg --query properties.endpoint
az cognitiveservices account keys list --name rfp-openai --resource-group rfp-eval-rg
```

**Step 2: Create Azure Database for PostgreSQL**
```bash
az postgres flexible-server create \
  --name rfp-postgres \
  --resource-group rfp-eval-rg \
  --location uksouth \
  --admin-user rfpadmin \
  --admin-password <strong-password> \
  --sku-name Standard_D2s_v3 \
  --tier GeneralPurpose \
  --storage-size 32 \
  --version 15

# Get connection string
az postgres flexible-server show-connection-string --server-name rfp-postgres
```

**Step 3: Run database migrations**
```bash
DATABASE_URL="postgresql://rfpadmin:<pass>@rfp-postgres.postgres.database.azure.com:5432/postgres?sslmode=require" \
python scripts/migrate.py
```

**Step 4: Build and push container**
```bash
# Create Azure Container Registry
az acr create --name rfpacr --resource-group rfp-eval-rg --sku Basic

# Build and push
az acr build --registry rfpacr --image rfp-api:latest .
```

**Step 5: Configure .env (Azure profile)**
```env
LLM_PROVIDER=azure
AZURE_OPENAI_API_KEY=<key-from-step-1>
AZURE_OPENAI_ENDPOINT=https://rfp-openai.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-02-01
AZURE_OPENAI_DEPLOYMENT=gpt-4o

EMBEDDING_PROVIDER=azure
# Azure embedding uses same endpoint and key

RERANKER_PROVIDER=bge
OBSERVABILITY_PROVIDER=langfuse

DATABASE_URL=postgresql://rfpadmin:<pass>@rfp-postgres.postgres.database.azure.com:5432/postgres?sslmode=require
QDRANT_URL=https://<cluster>.qdrant.io
QDRANT_API_KEY=<key>
JWT_SECRET_KEY=<random-64-chars>
SSL_VERIFY=true
```

**Step 6: Deploy to Azure Container Apps**
```bash
az containerapp env create \
  --name rfp-env \
  --resource-group rfp-eval-rg \
  --location uksouth

az containerapp create \
  --name rfp-api \
  --resource-group rfp-eval-rg \
  --environment rfp-env \
  --image rfpacr.azurecr.io/rfp-api:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 5 \
  --env-vars LLM_PROVIDER=azure \
             AZURE_OPENAI_API_KEY=secretref:azure-openai-key \
             ...
```

**Step 7: Deploy Next.js frontend to Azure Static Web Apps**
```bash
az staticwebapp create \
  --name rfp-frontend \
  --resource-group rfp-eval-rg \
  --source https://github.com/<your-repo> \
  --branch main \
  --app-location frontend \
  --output-location .next
```

**Step 8: Verify**
```bash
curl https://rfp-api.<region>.azurecontainerapps.io/health
```

### Data Residency
All data stays in `uksouth` (or your chosen Azure region). Azure OpenAI processes prompts in-region. No data crosses Azure region boundaries unless you configure geo-redundancy.

### Cost at this profile
- Azure OpenAI: pay per token (~$0.002–0.01/1K tokens depending on model)
- Azure Database for PostgreSQL: ~$50–150/month
- Azure Container Apps: ~$30–100/month (auto-scaled)
- Qdrant Cloud: $25–200/month
- **Total: ~$150–500/month** (dominated by Azure OpenAI token cost at volume)

---

## Profile 3 — Amazon Web Services (AWS)

### What it uses
- LLM: OpenAI GPT-4o via API (or Amazon Bedrock Claude)
- Embeddings: Local BGE (runs in ECS task, no API cost)
- Reranker: BGE local
- API: ECS Fargate (serverless containers)
- Storage: Amazon RDS PostgreSQL + Qdrant Cloud
- Observability: LangFuse Cloud or stdout → CloudWatch

### Step-by-Step Deploy

**Step 1: Create ECR repository and push image**
```bash
aws ecr create-repository --repository-name rfp-api --region eu-west-2

# Authenticate Docker to ECR
aws ecr get-login-password --region eu-west-2 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.eu-west-2.amazonaws.com

# Build and push
docker build -t rfp-api .
docker tag rfp-api:latest <account-id>.dkr.ecr.eu-west-2.amazonaws.com/rfp-api:latest
docker push <account-id>.dkr.ecr.eu-west-2.amazonaws.com/rfp-api:latest
```

**Step 2: Create RDS PostgreSQL**
```bash
aws rds create-db-instance \
  --db-instance-identifier rfp-postgres \
  --db-instance-class db.t4g.medium \
  --engine postgres \
  --engine-version 15 \
  --master-username rfpadmin \
  --master-user-password <strong-password> \
  --allocated-storage 20 \
  --storage-type gp3 \
  --region eu-west-2 \
  --no-publicly-accessible

# Get endpoint
aws rds describe-db-instances --db-instance-identifier rfp-postgres \
  --query 'DBInstances[0].Endpoint.Address'
```

**Step 3: Store secrets in AWS Secrets Manager**
```bash
aws secretsmanager create-secret \
  --name rfp/openai-api-key \
  --secret-string '{"api_key":"<your-openai-key>"}' \
  --region eu-west-2

aws secretsmanager create-secret \
  --name rfp/jwt-secret \
  --secret-string '{"key":"<random-64-chars>"}' \
  --region eu-west-2
```

**Step 4: Configure .env (AWS profile)**
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=<key>
OPENAI_MODEL=gpt-4o

EMBEDDING_PROVIDER=local
# Local BGE runs inside the ECS container — no external API

RERANKER_PROVIDER=bge

OBSERVABILITY_PROVIDER=stdout
# stdout → CloudWatch Logs automatically in ECS

DATABASE_URL=postgresql://rfpadmin:<pass>@<rds-endpoint>:5432/postgres
QDRANT_URL=https://<cluster>.qdrant.io
QDRANT_API_KEY=<key>
JWT_SECRET_KEY=<key>
```

**Step 5: Create ECS cluster and task definition**
```bash
aws ecs create-cluster --cluster-name rfp-cluster --region eu-west-2

# Create task definition (use ecs-task-definition.json in repo)
aws ecs register-task-definition \
  --cli-input-json file://scripts/ecs-task-definition.json \
  --region eu-west-2

# Create service with Application Load Balancer
aws ecs create-service \
  --cluster rfp-cluster \
  --service-name rfp-api \
  --task-definition rfp-api:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=<tg-arn>,containerName=rfp-api,containerPort=8000" \
  --region eu-west-2
```

**Step 6: Run migrations**
```bash
# Run as one-off ECS task
aws ecs run-task \
  --cluster rfp-cluster \
  --task-definition rfp-migrate:1 \
  --launch-type FARGATE \
  --overrides '{"containerOverrides":[{"name":"rfp-api","command":["python","scripts/migrate.py"]}]}' \
  --region eu-west-2
```

**Step 7: Deploy frontend to S3 + CloudFront**
```bash
cd frontend && npm run build && npm run export

aws s3 sync out/ s3://rfp-frontend-bucket --delete

aws cloudfront create-invalidation \
  --distribution-id <dist-id> \
  --paths "/*"
```

**Step 8: Verify**
```bash
curl https://<alb-dns>/health
```

### Cost at this profile
- OpenAI API: pay per token (~$0.002–0.01/1K tokens)
- RDS PostgreSQL db.t4g.medium: ~$50/month
- ECS Fargate (2 tasks): ~$60/month
- CloudFront + S3: ~$5/month
- **Total: ~$150–300/month** + OpenAI API cost

---

## Profile 4 — Google Cloud Platform (GCP)

### What it uses
- LLM: Vertex AI Gemini 1.5 Pro (or OpenAI via API)
- Embeddings: Vertex AI `text-embedding-004` or local BGE
- Reranker: BGE local
- API: Cloud Run (serverless containers)
- Storage: Cloud SQL PostgreSQL + Qdrant Cloud
- Observability: LangFuse Cloud or stdout → Cloud Logging

### Step-by-Step Deploy

**Step 1: Enable required GCP APIs**
```bash
gcloud auth login
gcloud config set project <your-project-id>

gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com
```

**Step 2: Create Artifact Registry and push image**
```bash
gcloud artifacts repositories create rfp-repo \
  --repository-format=docker \
  --location=europe-west2

gcloud auth configure-docker europe-west2-docker.pkg.dev

docker build -t europe-west2-docker.pkg.dev/<project>/rfp-repo/rfp-api:latest .
docker push europe-west2-docker.pkg.dev/<project>/rfp-repo/rfp-api:latest
```

**Step 3: Create Cloud SQL PostgreSQL**
```bash
gcloud sql instances create rfp-postgres \
  --database-version=POSTGRES_15 \
  --tier=db-g1-small \
  --region=europe-west2 \
  --no-assign-ip \
  --network=default

gcloud sql databases create rfp_eval --instance=rfp-postgres
gcloud sql users create rfpadmin --instance=rfp-postgres --password=<strong-password>

# Get connection string
gcloud sql instances describe rfp-postgres --format='get(connectionName)'
# Returns: <project>:europe-west2:rfp-postgres
```

**Step 4: Store secrets in Secret Manager**
```bash
echo -n "<openai-api-key>" | \
  gcloud secrets create openai-api-key --data-file=-

echo -n "<jwt-secret>" | \
  gcloud secrets create jwt-secret --data-file=-
```

**Step 5: Configure .env (GCP + Vertex AI profile)**
```env
# Option A: Vertex AI Gemini
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<key>
OPENROUTER_MODEL=google/gemini-1.5-pro

# Option B: OpenAI (simpler, no Vertex setup)
LLM_PROVIDER=openai
OPENAI_API_KEY=<key>

EMBEDDING_PROVIDER=local
# BGE local runs in Cloud Run container

RERANKER_PROVIDER=bge

OBSERVABILITY_PROVIDER=stdout
# stdout → Cloud Logging automatically in Cloud Run

# Cloud SQL via Cloud SQL Auth Proxy (automatically injected in Cloud Run)
DATABASE_URL=postgresql://rfpadmin:<pass>@/rfp_eval?host=/cloudsql/<connection-name>

QDRANT_URL=https://<cluster>.qdrant.io
QDRANT_API_KEY=<key>
JWT_SECRET_KEY=<key>
```

**Step 6: Deploy to Cloud Run**
```bash
gcloud run deploy rfp-api \
  --image europe-west2-docker.pkg.dev/<project>/rfp-repo/rfp-api:latest \
  --region europe-west2 \
  --platform managed \
  --port 8000 \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 1 \
  --max-instances 10 \
  --allow-unauthenticated \
  --add-cloudsql-instances <project>:europe-west2:rfp-postgres \
  --set-secrets="OPENAI_API_KEY=openai-api-key:latest,JWT_SECRET_KEY=jwt-secret:latest" \
  --set-env-vars="LLM_PROVIDER=openai,EMBEDDING_PROVIDER=local,..."
```

**Step 7: Run database migrations**
```bash
gcloud run jobs create rfp-migrate \
  --image europe-west2-docker.pkg.dev/<project>/rfp-repo/rfp-api:latest \
  --region europe-west2 \
  --add-cloudsql-instances <project>:europe-west2:rfp-postgres \
  --set-secrets="DATABASE_URL=db-url:latest" \
  --command python \
  --args scripts/migrate.py

gcloud run jobs execute rfp-migrate --region europe-west2
```

**Step 8: Deploy frontend to Firebase Hosting**
```bash
npm install -g firebase-tools
firebase login

cd frontend
npm run build

firebase init hosting
# Select: existing project, out directory, single-page app: yes

firebase deploy
```

**Step 9: Verify**
```bash
curl https://rfp-api-<hash>-ew.a.run.app/health
```

### Vertex AI Native (Optional — instead of OpenAI/OpenRouter)

Add Vertex AI as an LLM provider (not yet built — requires adding to `llm_provider.py`):

```python
# Planned addition to app/core/llm_provider.py
elif provider == "vertex":
    from google.cloud import aiplatform
    from vertexai.generative_models import GenerativeModel
    # Vertex AI Gemini 1.5 Pro
    # Note: uses google-cloud-aiplatform SDK, not openai SDK
    # Response format differs — requires separate handling
```

For now, use `LLM_PROVIDER=openrouter` with `OPENROUTER_MODEL=google/gemini-1.5-pro` to access Gemini via OpenAI-compatible API.

### Cost at this profile
- Cloud Run (2 vCPU, 2GB, min 1 instance): ~$40/month
- Cloud SQL db-g1-small: ~$30/month
- Firebase Hosting: Free tier sufficient
- OpenAI API: pay per token
- **Total: ~$100–250/month** + LLM API cost

---

## Profile 5 — Air-Gapped / On-Premises

### What it uses
- LLM: Ollama running Qwen 2.5 7B or 14B (fits on 16–24GB VRAM consumer GPU)
- Embeddings: Local BGE (CPU, in-process)
- Reranker: BGE local (CPU)
- API: FastAPI on local server
- Storage: PostgreSQL on local server + Qdrant on local Docker
- Observability: stdout JSON (pipe to local ELK / Splunk)

### Step-by-Step Deploy

**Step 1: Install Ollama and download model**
```bash
# On the local inference server (Linux recommended)
curl -fsSL https://ollama.ai/install.sh | sh

# Download Qwen 2.5 7B (fits in 8GB VRAM)
ollama pull qwen2.5:7b

# Or Qwen 2.5 14B (fits in 16GB VRAM)
ollama pull qwen2.5:14b

# Start Ollama server (default: localhost:11434)
ollama serve
```

**Step 2: Configure .env**
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b

EMBEDDING_PROVIDER=local
RERANKER_PROVIDER=bge
OBSERVABILITY_PROVIDER=stdout

DATABASE_URL=postgresql://rfpadmin:pass@localhost:5432/rfp_eval
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
JWT_SECRET_KEY=<random-64-chars>
SSL_VERIFY=false  # Internal network only
```

**Step 3: Start local stack**
```bash
docker-compose up -d  # Starts Qdrant + PostgreSQL
python scripts/migrate.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**No internet access required after initial setup.**

---

## Switching Between Profiles (Live)

The platform is designed so any provider switch requires only:
1. Update `.env`
2. Restart FastAPI

No database migration. No code change. No Qdrant re-indexing (unless switching embedding model — then re-ingest).

```bash
# Example: Switch from OpenAI to Modal mid-flight
# 1. Edit .env: LLM_PROVIDER=modal + MODAL_LLM_ENDPOINT=...
# 2. Restart:
systemctl restart rfp-api
# or
gcloud run deploy rfp-api --image ... --set-env-vars LLM_PROVIDER=modal,...
```

---

## Provider Comparison for Decision-Making

| Criterion | Modal | Azure | AWS | GCP | Air-gapped |
|---|---|---|---|---|---|
| Time to first deploy | 30 min | 2–3 hours | 2–3 hours | 2–3 hours | 1 hour |
| Per-token cost | None (GPU-hour) | Yes | Yes | Yes | None |
| Fine-tuning path | Yes (A100) | Partial (fine-tuning API) | No | Partial (Vertex) | Yes (Ollama) |
| Data stays on-prem | No | Yes (in-region) | Yes (in-region) | Yes (in-region) | Yes |
| Air-gapped capable | No | No | No | No | Yes |
| UK data residency | No | Yes (UK South) | Yes (EU-West) | Yes (EU-West) | Yes |
| NHS / Gov approved | No | Yes (G-Cloud) | Partial | No | Yes |
| Cold start | 5–10 min (A100) | None | None | None | None |
| Best for | Demo, cost-opt | Enterprise EU | AWS-native | GCP-native | NHS, gov |
