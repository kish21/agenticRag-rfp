# CLAUDE.md
# Read this completely at the start of every session.
# These are constraints, not suggestions.
# Last updated: [UPDATE AFTER EVERY SESSION]

---

## THIS PROJECT

**Product:** Enterprise Agentic AI Platform — RFP Evaluation Agent (first agent)
**Architecture:** 9-agent multi-agent system with structured outputs and critic guardrails
**Tech stack finalised:** LangGraph + LlamaIndex + Qdrant + Cohere Rerank + ColBERT + PostgreSQL + FastAPI + Modal + LangSmith + LangFuse + Next.js

---

## THE NINE AGENTS — DO NOT MERGE, DO NOT SKIP

```
1. Planner Agent       — decomposes evaluation into typed task DAG            [Skill 02]
2. Ingestion Agent     — LlamaIndex → Qdrant, triggers Extraction at ingestion [Skill 03]
3. Retrieval Agent     — hybrid search + Cohere Rerank v3 + HyDE               [Skill 03b]
4. Extraction Agent    — structured facts → PostgreSQL immediately              [Skill 04]
5. Evaluation Agent    — reads PostgreSQL facts, NOT Qdrant chunks              [Skill 05]
6. Comparator Agent    — SQL join cross-vendor, rank stability tested           [Skill 05]
7. Decision Agent      — governance routing, approval tiers from config         [Skill 06]
8. Explanation Agent   — grounded report, every claim cited to source           [Skill 06]
9. Critic Agent        — runs after EVERY agent, hard/soft/log/escalate        [Skill 02]
```

Every agent has its own Pydantic output model. No agent passes raw text.
Every fact has a grounding_quote. Every decision has evidence_citations.
The Critic Agent is the only agent that can block the pipeline.

---

## MULTI-LLM PROVIDER SUPPORT

Customers configure their LLM by setting LLM_PROVIDER in .env.
Zero engine code changes. Built in app/core/llm_provider.py (created in Skill 01, Step 9b).

| Provider value | Uses | Notes |
|---|---|---|
| `openai` | GPT-4o via openai 2.x | Default. response_format JSON supported |
| `anthropic` | Claude via anthropic 0.49 | Prompt-based JSON (no response_format) |
| `openrouter` | Any model via OpenRouter API | 200+ models, openai SDK with different base_url |
| `ollama` | Qwen 2.5, Llama 3, Mistral locally | No API key, openai-compatible API |

Agents call `call_llm()` — never import provider SDKs directly in agent files.
Embeddings always use OpenAI text-embedding-3-large regardless of LLM_PROVIDER.

## MODAL DEPLOYMENT

Two deployment surfaces:
- **FastAPI** (local or any cloud): real-time API, agent orchestration, retrieval
- **Modal** (`app_modal.py`): heavy PDF extraction, scheduled cleanup, rate monitoring

Modal routes: PDFs >50 pages or scanned PDFs → Modal for burst CPU/OCR
Modal schedules: daily cleanup, 30-minute rate monitoring

File: `app_modal.py` (created in Skill 01, Step 11)

## TWO STORAGE LAYERS — BOTH REQUIRED

```
Qdrant          — vector embeddings for semantic search
                  dense (semantic) + sparse (BM25) vectors per chunk
                  filters by org_id + vendor_id + section_type + priority

PostgreSQL      — structured facts extracted from documents
                  extracted_certifications, extracted_insurance,
                  extracted_slas, extracted_projects, extracted_pricing,
                  extracted_facts (generic)
                  Every row has source_chunk_id linking back to Qdrant
```

ChromaDB is gone. Replaced by Qdrant.
The Evaluation Agent reads PostgreSQL facts, NOT Qdrant chunks directly.

---

## THE THREE DAY-ONE FAILURES TO BUILD FIRST

Before anything else in Skill 04:
1. RFP identity confirmation step (2 hours — prevents wrong document)
2. Human override mechanism with audit trail (1 day — prevents corrupt audit)
3. Rate limit handler with exponential backoff (half day — prevents mid-run failure)

---

## CURRENT BUILD STATE

**Current skill:** SKILL_01
**Last verified checkpoint:** none — not started
**Next action:** Follow SKILL_01_FOUNDATION.md Step 1
**Blockers:** none

---

## SESSION START — MANDATORY BEFORE ANY CODE

```bash
python checkpoint_runner.py status
python drift_detector.py
python contract_tests.py
```

Then state: "I will build [FILE] to pass checkpoint [SKILL-CPxx]"
Wait for confirmation before starting.

---

## SCOPE RULES

**Allowed:**
- Build exactly what the current skill step says
- Run checkpoint after every file
- Add to BACKLOG.md if you notice something extra

**Hard stops — ask user first:**
- Installing packages not in requirements.txt
- Merging any two agents into one
- Hardcoding any fact, clause, weight, or threshold in agent files
- Skipping the Critic Agent check after any agent output
- Proceeding past a failing checkpoint

---

## COMPONENT CONTRACTS — NEVER BREAK

1. Every agent output is a Pydantic BaseModel — never raw text
2. Every extracted fact has a grounding_quote that appears verbatim in source
3. Every agent reads org_id + vendor_id filters — never cross-tenant
4. Critic Agent runs after every agent — never skip
5. Config drives all agent behaviour — no hardcoded business logic
6. PostgreSQL stores structured facts — Qdrant stores raw chunks only
7. Human override creates an AuditOverride record — never direct DB edit

---

## FILE OWNERSHIP MAP

```
Skill 01: requirements.txt, .env, docker-compose.yml, app/config.py, app/main.py
Skill 02: app/agents/planner.py, app/agents/critic.py
          app/core/qdrant_client.py, app/core/rate_limiter.py
          app/api/auth.py, app/api/routes.py, app_modal.py
Skill 03: app/agents/ingestion.py, app/core/llamaindex_pipeline.py
          app/core/ingestion_validator.py
Skill 03b: app/agents/retrieval.py, app/core/reranker.py
           app/core/query_rewriter.py, app/core/hyde.py
           app/core/context_optimizer.py
Skill 04: app/agents/extraction.py, app/core/output_models.py
          app/db/schema.sql, app/db/fact_store.py
Skill 05: app/agents/evaluation.py, app/agents/comparator.py
Skill 06: app/agents/decision.py, app/agents/explanation.py
          app/core/override_mechanism.py, app/core/rfp_confirmation.py
Skill 07: app/output/pdf_report.py, frontend/ (Next.js)
          tests/regression/
Skill 08: app/core/langfuse_client.py, app/jobs/cleanup.py
          app/jobs/rate_monitor.py
Skill 09: app/core/agent_registry.py, app/api/admin_routes.py
          app/agents/hr_agent_config.py
```

---

## SESSION END — MANDATORY

```bash
python checkpoint_runner.py status
python drift_detector.py
```

Update four fields above. Add one line to daily_build_log.md.

---

## VERIFIED PACKAGE VERSIONS — April 2026 (grounded from PyPI)

```
openai==2.33.0          langchain==1.2.16       langgraph==0.4.1
langsmith==0.7.37       langfuse==4.5.1         llama-index-core==0.12.6
qdrant-client==1.14.2   cohere==5.21.1          sentence-transformers==4.1.0
fastapi==0.136.1        pydantic==2.11.3        sqlalchemy==2.0.40
uvicorn[standard]==0.34.3  psycopg2-binary==2.9.10  httpx==0.28.1
```

**Critical API changes — will break if wrong version used:**
- `langfuse` 2.x → 4.x: SDK rewritten — read migration guide before Skill 08
- `cohere`: `cohere.Client()` deprecated → use `cohere.ClientV2()`
- `qdrant-client`: `client.search()` deprecated → use `client.query_points()`
- `pydantic`: `@validator` deprecated → use `@field_validator` (all skill code uses v2 style)
- `ragatouille`: removed from requirements — unmaintained, use sentence-transformers CrossEncoder
