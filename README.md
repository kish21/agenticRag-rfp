# Enterprise Vendor Governance & Spend Intelligence Platform

> AI-powered vendor evaluation with CEO-level spend visibility across departments and regions.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-green)
![LangGraph](https://img.shields.io/badge/LangGraph-1.1.10-orange)
![Qdrant](https://img.shields.io/badge/Qdrant-1.14-red)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)
![Modal](https://img.shields.io/badge/Modal-GPU-purple)
![Next.js](https://img.shields.io/badge/Next.js-Frontend-black)

---

## What It Does

Large enterprises run RFP evaluations in silos — IT in Singapore, HR in Germany, and Marketing in the US each evaluate vendors independently, with no shared intelligence. The result: duplicate contracts, regional pricing inconsistencies, and a CEO who has no visibility into what the company is committing to spend until the quarterly CFO report.

This platform replaces the manual, siloed process with a 9-agent AI pipeline that evaluates vendor documents in under 45 minutes, extracts structured facts with verbatim source grounding, and surfaces the results to an executive dashboard showing real-time spend commitment, duplicate vendor alerts, and pricing anomalies — across every department and region, in one view.

---

## Key Features

- **CEO Dashboard** — real-time view of active RFPs, committed vendor spend, duplicate vendor alerts, and cross-region pricing anomaly detection across all departments and regions
- **9-Agent Pipeline** — Planner → Ingestion → Retrieval → Extraction → Evaluation → Comparator → Decision → Explanation → Critic, each with a typed Pydantic output model
- **Grounded Extraction** — every extracted fact contains a verbatim quote from the source document; the Critic agent hard-blocks the pipeline if a grounding check fails
- **Full Audit Trail** — every vendor decision and every human override is recorded in an immutable audit log, retained for 7 years
- **Multi-Tenant** — org_id isolation enforced at three independent layers: JWT extraction, PostgreSQL Row-Level Security, and Qdrant query filters
- **Multi-Cloud** — swap LLM, embedding, reranker, and observability providers via a single `.env` change; no code modifications required

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  CEO Dashboard (Next.js)  │  Procurement UI  │  Admin       │
│  · Global spend view      │  · Upload PDFs   │  · RBAC      │
│  · Duplicate alerts       │  · Review facts  │  · Tenants   │
│  · Pricing anomalies      │  · Override      │  · Settings  │
└──────────────────────────────┬──────────────────────────────┘
                               │ JWT / HTTPS
                    ┌──────────▼──────────┐
                    │   FastAPI + Auth     │
                    └──────────┬──────────┘
                               │
          ┌────────────────────▼────────────────────┐
          │         LangGraph — 9 Agents             │
          │                                          │
          │  [1] Planner ──► [2] Ingestion           │
          │       │                │                 │
          │  [9] Critic ◄──────────▼                 │
          │       │          [3] Retrieval            │
          │       │                │                 │
          │  [9] Critic ◄──────────▼                 │
          │       │          [4] Extraction           │
          │       │                │                 │
          │  [9] Critic ◄──────────▼                 │
          │       │   [5] Evaluation → [6] Comparator│
          │       │                │                 │
          │  [9] Critic ◄──── [7] Decision           │
          │       │                │                 │
          │  [9] Critic ◄──── [8] Explanation        │
          └────────────┬───────────────┬─────────────┘
                       │               │
          ┌────────────▼────┐ ┌────────▼────────────┐
          │  Qdrant          │ │  PostgreSQL          │
          │  Dense + Sparse  │ │  Structured facts    │
          │  vectors         │ │  Evaluation scores   │
          │  org_id filtered │ │  Audit trail (RLS)   │
          └─────────────────┘ └─────────────────────┘
                       │
          ┌────────────▼────────────────────────────┐
          │  Modal (Serverless GPU)                  │
          │  · PDF extraction — CPU burst            │
          │  · Batch embedding — A10G GPU            │
          │  · LLM inference — A100-80GB (Qwen 72B) │
          └─────────────────────────────────────────┘
```

---

## Tech Stack

| Category | Technology |
|---|---|
| **Orchestration** | LangGraph 1.1.10 |
| **Document parsing** | LlamaIndex 0.12.6 (HierarchicalNodeParser + SentenceWindowNodeParser) |
| **Vector store** | Qdrant 1.14 — dense + sparse (BM25), Reciprocal Rank Fusion |
| **Reranker** | BAAI/bge-reranker-v2-m3 (local CrossEncoder) — swappable to Cohere |
| **Retrieval** | HyDE + query rewriting + hybrid search |
| **Structured storage** | PostgreSQL 15 + SQLAlchemy 2.0 + Row-Level Security |
| **LLM** | Configurable — OpenAI, Anthropic, Azure, OpenRouter, Ollama, Modal vLLM |
| **Embeddings** | Configurable — OpenAI text-embedding-3-large, Azure, local BGE, Modal A10G |
| **Burst compute** | Modal (PDF OCR on CPU, embeddings on A10G, Qwen 2.5 72B AWQ on A100) |
| **API** | FastAPI 0.136 + Uvicorn |
| **Schema validation** | Pydantic 2.11 throughout — every agent output is a typed model |
| **Frontend** | Next.js |
| **Observability** | LangSmith (LLM tracing) + LangFuse (agent logging) — swappable |
| **Auth** | JWT with org_id scoping |

---

## Quick Start

```bash
# 1. Start Qdrant + PostgreSQL
docker-compose up -d

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set LLM_PROVIDER and API keys

# 4. Run database migrations
python scripts/migrate.py

# 5. Start the API
uvicorn app.main:app --reload --port 8000
```

Frontend:
```bash
cd frontend && npm install && npm run dev
```

---

## Configuration — Provider Switching

Switch any provider via `.env` only. No code changes. No restart of other services.

| Variable | Options |
|---|---|
| `LLM_PROVIDER` | `openai` · `anthropic` · `azure` · `openrouter` · `ollama` · `modal` |
| `EMBEDDING_PROVIDER` | `openai` · `azure` · `local` · `modal` |
| `RERANKER_PROVIDER` | `bge` · `cohere` · `colbert` · `none` |
| `OBSERVABILITY_PROVIDER` | `langfuse` · `stdout` · `none` |

Example — switch from OpenAI to Azure with no code changes:
```env
LLM_PROVIDER=azure
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
EMBEDDING_PROVIDER=azure
```

---

## Cloud Deployment

Step-by-step CLI deployment guides for all platforms:

| Platform | Guide |
|---|---|
| Modal (Qwen 2.5 72B, no per-token cost) | [docs/product/phase5_deployment/05_multi_cloud_deployment_guide.md#profile-1--modal](docs/product/phase5_deployment/05_multi_cloud_deployment_guide.md) |
| Microsoft Azure (GPT-4o, EU data residency) | [docs/product/phase5_deployment/05_multi_cloud_deployment_guide.md#profile-2--microsoft-azure](docs/product/phase5_deployment/05_multi_cloud_deployment_guide.md) |
| Amazon Web Services (ECS Fargate) | [docs/product/phase5_deployment/05_multi_cloud_deployment_guide.md#profile-3--amazon-web-services-aws](docs/product/phase5_deployment/05_multi_cloud_deployment_guide.md) |
| Google Cloud Platform (Cloud Run) | [docs/product/phase5_deployment/05_multi_cloud_deployment_guide.md#profile-4--google-cloud-platform-gcp](docs/product/phase5_deployment/05_multi_cloud_deployment_guide.md) |
| Air-gapped / On-premises (Ollama, no internet) | [docs/product/phase5_deployment/05_multi_cloud_deployment_guide.md#profile-5--air-gapped--on-premises](docs/product/phase5_deployment/05_multi_cloud_deployment_guide.md) |

---

## Documentation

Full product lifecycle documentation — 32 documents across 6 phases — is in [`docs/product/`](docs/product/INDEX.md):

| Phase | Contents |
|---|---|
| Strategy | Business case, stakeholder map, user personas, competitive analysis |
| Requirements | PRD, functional & non-functional requirements, OKRs, KRAs, data requirements |
| Architecture | System architecture, agent tech stack, configuration guide, security model, 5 ADRs |
| Build | Evaluation framework, prompt registry, observability plan, test plan |
| Deployment | Deployment runbook, incident response, AI governance, RBAC design, multi-cloud guide |
| Post-Launch | Retrospective, product roadmap, capacity planning, technical assessment |

---

## Project Structure

```
agenticRag-rfp/
├── app/
│   ├── agents/          # 9 agents — planner, ingestion, retrieval, extraction,
│   │                    #   evaluation, comparator, decision, explanation, critic
│   ├── core/            # Provider abstractions — llm, embedding, reranker,
│   │                    #   observability, auth, rate_limiter, org_settings
│   ├── config/          # product.yaml (agent behaviour), platform.yaml (infra)
│   ├── db/              # schema.sql, fact_store.py (PostgreSQL writes)
│   ├── api/             # FastAPI routes, admin routes
│   └── jobs/            # rate_monitor.py, cleanup.py (Modal scheduled)
├── app_modal.py         # Modal deployment — PDF, embedding, LLM functions
├── frontend/            # Next.js — CEO dashboard, procurement UI, admin console
├── docs/product/        # Full product lifecycle documentation (32 files)
├── tests/               # Contract tests, checkpoint runner, regression tests
├── scripts/             # migrate.py, reset_dev_data.py, debug_run.py
└── docker-compose.yml   # Local dev — Qdrant + PostgreSQL
```

---

## Verified Package Versions

```
openai==2.33.0        langchain==1.2.16      langgraph==1.1.10
langsmith==0.7.37     langfuse==4.5.1        llama-index-core==0.12.6
qdrant-client==1.14.2 cohere==5.21.1         sentence-transformers==4.1.0
fastapi==0.136.1      pydantic==2.11.3       sqlalchemy==2.0.40
```
