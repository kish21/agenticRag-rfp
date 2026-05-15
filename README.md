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

## Build Status

| Area | Component | Status |
|---|---|---|
| **Agent Pipeline** | All 9 agents (Planner → Ingestion → Retrieval → Extraction → Evaluation → Comparator → Decision → Explanation → Critic) | ✅ Built |
| | Critic topology — wired after every agent, enforced at graph compile time | ✅ Built |
| | Provider abstraction — LLM, embedding, reranker, observability via `.env` | ✅ Built |
| | Grounding enforcement + whitespace normalisation fix | ✅ Built |
| | Human override with immutable audit trail | ✅ Built |
| | Rate limiter with exponential backoff | ✅ Built |
| | Per-org settings (org_settings) with 60s TTL cache | ✅ Built |
| **Storage** | Qdrant hybrid search — dense + sparse BM25 + Reciprocal Rank Fusion | ✅ Built |
| | PostgreSQL structured facts + Row-Level Security | ✅ Built |
| | Full lineage: decision → fact → source chunk (source_chunk_id) | ✅ Built |
| **Frontend** | CEO spend dashboard — active RFPs, committed spend, duplicate alerts, pricing anomalies | 🚧 Partial |
| | Procurement UI — upload, trigger evaluation, review extractions, apply overrides | 🚧 Partial |
| | Admin console — tenant management, RBAC, org settings | 🚧 Partial |
| | Real-time WebSocket push (currently polling refresh) | 📋 Planned |
| | Mobile-responsive layout | 📋 Planned |
| **Deployment** | Local dev — Docker Compose (Qdrant + PostgreSQL) | ✅ Built |
| | Modal serverless GPU — PDF OCR, batch embeddings, Qwen 2.5 72B on A100 | ✅ Built |
| | Cloud deployment — Azure / AWS / GCP / Air-gapped (runbooks written, not yet executed) | 📋 Planned |
| | CI/CD pipeline | 📋 Planned |
| **Quality** | Contract tests + checkpoint runner | ✅ Built |
| | Unit and integration test suite | 🚧 Partial |
| | Held-out retrieval and extraction benchmarks (annotated ground truth) | 📋 Planned |
| | Load testing (locust / k6) | 📋 Planned |

---

## Documentation

Full product lifecycle documentation — 32 documents across 6 phases:

| Phase | Documents |
|---|---|
| [**Strategy**](docs/product/phase1_strategy/) | [Business Case](docs/product/phase1_strategy/01_business_case.md) · [Stakeholder Map](docs/product/phase1_strategy/02_stakeholder_map.md) · [Current State Process](docs/product/phase1_strategy/03_current_state_process.md) · [User Personas](docs/product/phase1_strategy/04_user_personas.md) · [Competitive Analysis](docs/product/phase1_strategy/05_competitive_analysis.md) |
| [**Requirements**](docs/product/phase2_requirements/) | [PRD](docs/product/phase2_requirements/01_prd.md) · [Functional Requirements](docs/product/phase2_requirements/02_functional_requirements.md) · [Non-Functional Requirements](docs/product/phase2_requirements/03_non_functional_requirements.md) · [OKRs](docs/product/phase2_requirements/04_okrs.md) · [KRAs](docs/product/phase2_requirements/05_kras.md) · [Data Requirements](docs/product/phase2_requirements/06_data_requirements.md) |
| [**Architecture**](docs/product/phase3_architecture/) | [System Architecture](docs/product/phase3_architecture/01_system_architecture.md) · [Agent Tech Stack](docs/product/phase3_architecture/02_agent_tech_stack.md) · [Configuration Guide](docs/product/phase3_architecture/03_configuration_guide.md) · [Security Model](docs/product/phase3_architecture/04_security_trust_model.md) · [5 ADRs](docs/product/phase3_architecture/adrs/) |
| [**Build**](docs/product/phase4_build/) | [Evaluation Framework](docs/product/phase4_build/01_evaluation_framework.md) · [Prompt Registry](docs/product/phase4_build/02_prompt_registry.md) · [Observability Plan](docs/product/phase4_build/03_observability_plan.md) · [Test Plan](docs/product/phase4_build/04_test_plan.md) |
| [**Deployment**](docs/product/phase5_deployment/) | [Deployment Runbook](docs/product/phase5_deployment/01_deployment_runbook.md) · [Incident Response](docs/product/phase5_deployment/02_incident_response.md) · [AI Governance](docs/product/phase5_deployment/03_ai_governance.md) · [RBAC Design](docs/product/phase5_deployment/04_rbac_design.md) · [Multi-Cloud Guide](docs/product/phase5_deployment/05_multi_cloud_deployment_guide.md) |
| [**Post-Launch**](docs/product/phase6_post_launch/) | [Retrospective](docs/product/phase6_post_launch/01_retrospective.md) · [Product Roadmap](docs/product/phase6_post_launch/02_product_roadmap.md) · [Capacity Planning](docs/product/phase6_post_launch/03_capacity_planning.md) · [Technical Assessment](docs/product/phase6_post_launch/04_project_evaluation.md) |
| [**Developer Reference**](docs/dev/) | [Backlog](docs/dev/BACKLOG.md) · [Platform Decisions](docs/dev/PLATFORM_DECISIONS.md) · [Production Checklist](docs/dev/PRODUCTION_CHECKLIST.md) |

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
| **Document parsing** | LlamaIndex 0.14.21 (HierarchicalNodeParser + SentenceWindowNodeParser) |
| **Vector store** | Qdrant 1.17 — dense + sparse (BM25), Reciprocal Rank Fusion |
| **Reranker** | BAAI/bge-reranker-v2-m3 (local CrossEncoder) — swappable to Cohere |
| **Retrieval** | HyDE + query rewriting + hybrid search |
| **Structured storage** | PostgreSQL 15 + SQLAlchemy 2.0 + Row-Level Security |
| **LLM** | Configurable — OpenAI, Anthropic, Azure, OpenRouter, Ollama, Modal vLLM |
| **Embeddings** | Configurable — OpenAI text-embedding-3-large, Azure, local BGE, Modal A10G |
| **Burst compute** | Modal (PDF OCR on CPU, embeddings on A10G, Qwen 2.5 72B AWQ on A100) |
| **API** | FastAPI 0.136 + Uvicorn |
| **Schema validation** | Pydantic 2.13 throughout — every agent output is a typed model |
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
├── docs/
│   ├── dev/             # Backlog, platform decisions, production checklist
│   └── product/         # Full product lifecycle documentation (32 files, 6 phases)
├── tests/               # Contract tests, checkpoint runner, regression tests
├── scripts/             # migrate.py, reset_dev_data.py, debug_run.py
└── docker-compose.yml   # Local dev — Qdrant + PostgreSQL
```

---

## Verified Package Versions

```
openai==2.33.0        langchain==1.2.16      langgraph==1.1.10
langsmith==0.8.0      langfuse==4.5.1        llama-index-core==0.14.21
qdrant-client==1.17.1 cohere==5.21.1         sentence-transformers==4.1.0
fastapi==0.136.1      pydantic==2.13.3       sqlalchemy==2.0.40
```
