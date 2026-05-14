# Agent-by-Agent Tech Stack
*Version 1.0 — 2026-05-14*

---

## Overview

Each agent in the 9-agent pipeline uses a specific combination of libraries, models, storage, and infrastructure. This document maps exactly what technology each agent uses and why.

---

## Agent 1 — Planner Agent

**File:** `app/agents/planner.py`
**Role:** Decomposes the evaluation into a typed task DAG — which criteria to evaluate, in what order, for which vendors.

| Component | Technology | Why |
|---|---|---|
| Orchestration | LangGraph `StateGraph` | DAG topology with typed state |
| Output model | `PlannerOutput` (Pydantic v2) | Structured task list, no raw text |
| LLM | None — fully deterministic | Criteria list comes from config, not LLM generation |
| Config source | `app/config/product.yaml` + `org_settings` | Criteria loaded from config, not hardcoded |
| Critic check | `critic.py` — soft checks only | Validates task list is non-empty and well-formed |

**No LLM call.** Planner is deterministic — it reads criteria from config and constructs the task list structurally.

---

## Agent 2 — Ingestion Agent

**File:** `app/agents/ingestion.py`
**Core pipeline:** `app/core/llamaindex_pipeline.py`
**Role:** Ingests vendor PDF documents, chunks them, embeds them, stores in Qdrant.

| Component | Technology | Why |
|---|---|---|
| Document parsing | LlamaIndex `SimpleDirectoryReader` | Handles PDF + DOCX, metadata extraction |
| Chunking | LlamaIndex `HierarchicalNodeParser` (summary/detail/leaf) + `SentenceWindowNodeParser` | Multi-granularity: macro for context, micro for precision |
| Chunk size | 500 tokens, 50 overlap (platform.yaml) | Balances context window and retrieval precision |
| Dense embeddings | Configurable via `EMBEDDING_PROVIDER` (see below) | Swap without code changes |
| └ openai | `text-embedding-3-large`, 3072-dim, OpenAI SDK | Default — highest quality |
| └ azure | Same model via Azure OpenAI endpoint | Enterprise data residency |
| └ local | `BAAI/bge-large-en-v1.5`, 1024-dim, `sentence-transformers` | No API cost, CPU |
| └ modal | `BAAI/bge-large-en-v1.5`, 1024-dim, batch on A10G GPU | No API cost, fast batch |
| Sparse embeddings | BM25 TF-IDF approximation, 100K hash bins (in-process) | Keyword recall for exact compliance terms |
| Vector store | Qdrant `client.upsert()` via `app/core/qdrant_client.py` | Dense + sparse, org_id + vendor_id scoped |
| Collection naming | `{org_id}__{vendor_id}` | Enforces tenant isolation at collection level |
| OCR (scanned PDFs) | Modal CPU burst (`extract_pdf_on_modal`) | Avoids blocking FastAPI for heavy OCR |
| Validation | `app/core/ingestion_validator.py` | Checks chunk count, embedding dimensions, collection exists |
| Output model | `IngestionOutput` (Pydantic v2) | chunk_count, collection_name, status |
| Critic check | `critic.py` — validates chunk count > 0, collection named correctly | HARD block if empty |

---

## Agent 3 — Retrieval Agent

**File:** `app/agents/retrieval.py`
**Support files:** `app/core/hyde.py`, `app/core/query_rewriter.py`, `app/core/reranker_provider.py`
**Role:** For each criterion, retrieves the most relevant chunks from Qdrant.

| Component | Technology | Why |
|---|---|---|
| Query rewriting | LLM via `call_llm()` | Converts user criterion to formal procurement language before embedding |
| HyDE generation | LLM via `call_llm()` + `platform.yaml` hyde_templates | Generates hypothetical vendor response, embeds that instead of the criterion |
| HyDE templates | 3 templates in `platform.yaml`: vendor_response, rfp_requirement, policy_document | Domain-appropriate hypothetical documents |
| Dense retrieval | Qdrant `client.query_points()` with dense vector | Semantic similarity |
| Sparse retrieval | Qdrant `client.query_points()` with sparse vector | Keyword / BM25 match |
| Hybrid fusion | Reciprocal Rank Fusion (RRF, k=60) in Qdrant | Combines dense + sparse results without manual weight tuning |
| Candidate count | 20 before rerank (platform.yaml) | Wide net before precision reranking |
| Reranker | Configurable via `RERANKER_PROVIDER` | |
| └ bge (default) | `BAAI/bge-reranker-v2-m3`, `sentence-transformers CrossEncoder`, local CPU | No API cost, strong performance |
| └ cohere | Cohere Rerank v3 API (`rerank-english-v3.0`) | Strongest quality, API cost |
| └ colbert | ColBERT v2.0 via `sentence-transformers` | Token-level late interaction, local |
| └ none | Vector score order, no reranking | Dev/testing only |
| Rerank top-n | 5 (product.yaml preset) | Feed 5 best chunks to extraction |
| Retrieval Critic | `app/core/retrieval_critic.py` — LLM-based adequacy check | Verifies chunks contain specific facts criterion needs before extraction |
| Output model | `RetrievalOutput` (Pydantic v2) | chunks, scores, rerank_scores, adequacy |

---

## Agent 4 — Extraction Agent

**File:** `app/agents/extraction.py`
**Support files:** `app/core/extraction_critic.py`, `app/db/fact_store.py`
**Role:** Extracts structured facts from retrieved chunks, stores in PostgreSQL.

| Component | Technology | Why |
|---|---|---|
| LLM extraction | `call_llm()` — JSON prompt | Structured JSON output from chunk text |
| Response format | `{"type": "json_object"}` for OpenAI/Azure; prompt-based for Anthropic/Modal | Provider-aware — vLLM crashes with response_format |
| Fact types | certifications, insurance, SLAs, pricing, projects, generic | Covers primary procurement compliance categories |
| Grounding check | `re.sub(r'\s+', ' ', text).strip()` normalisation before containment check | PDF table cells produce multi-line text; LLM quotes with single spaces |
| Retry logic | 1 retry with tighter prompt if Extraction Critic flags inadequate | `platform.yaml: extraction_critic_max_retries: 1` |
| Storage | SQLAlchemy + `app/db/fact_store.py` → PostgreSQL | Structured facts enable SQL joins in Evaluation |
| RLS | `SET LOCAL app.org_id` on every connection | Row-Level Security at DB layer |
| Output model | `ExtractionOutput` (Pydantic v2) | facts_extracted, fact_types, grounding_status |
| Critic check | `app/core/extraction_critic.py` — LLM-based | Verifies extracted fact answers the criterion correctly, using the right fact type |

**Critical fix (do not revert):** Whitespace normalisation in `_hallucination_risk()` — PDF tables produce cells on separate lines; LLM joins them with spaces. Raw `\n` matching causes false hallucination flags.

---

## Agent 5 — Evaluation Agent

**File:** `app/agents/evaluation.py`
**Role:** Scores each vendor against each criterion using PostgreSQL facts.

| Component | Technology | Why |
|---|---|---|
| Data source | PostgreSQL `extracted_*` tables (NOT Qdrant) | Facts are structured, queryable, typed — chunks are unstructured |
| Scoring | LLM via `call_llm()` — rubric prompt | Criteria, thresholds, weights from config — no hardcoded scoring |
| Rubric | `org_settings.quality_tier` → `product.yaml presets` | Customer-configurable quality tier |
| Confidence | Per-criterion confidence score (0.0–1.0) | Retry if below `confidence_retry_threshold` (0.75) |
| Score bands | `product.yaml: score_bands` | strongly_recommended / recommended / acceptable / marginal |
| Evidence citations | List of `source_chunk_id` per score | Every score is traceable |
| Output model | `EvaluationOutput` (Pydantic v2) | vendor_id, criterion_scores, overall_score, confidence |
| Critic check | `critic.py` — validates confidence > floor, citations non-empty | HARD block if no evidence citations |

---

## Agent 6 — Comparator Agent

**File:** `app/agents/comparator.py`
**Role:** Ranks all vendors in the evaluation, identifies differentiators.

| Component | Technology | Why |
|---|---|---|
| Data source | SQL JOIN across `evaluation_scores` table | Cross-vendor comparison requires structured data |
| Ranking | Score sum with criterion weights | Deterministic weighted sum, not LLM opinion |
| Rank stability | `rank_margin_threshold` check (default: 3 points) | Flags when top-2 vendors are too close to call |
| Differentiators | LLM via `call_llm()` | Identifies what specifically separates top vendors |
| Score variance | `score_variance_threshold` check (default: 0.15) | Flags suspiciously uniform scores across criteria |
| Output model | `ComparatorOutput` (Pydantic v2) | ranked_vendors, differentiators, rank_margin_flag |
| Critic check | `critic.py` — validates ranking is complete, all vendors scored | SOFT flag if rank margin too narrow |

---

## Agent 7 — Decision Agent

**File:** `app/agents/decision.py`
**Support file:** `app/core/rfp_confirmation.py`
**Role:** Routes the evaluation to the correct human approver based on contract value.

| Component | Technology | Why |
|---|---|---|
| Approval tiers | Read from `org_settings` (not hardcoded) | Customer-configurable thresholds |
| Default tiers | <£100K → Dept Head, £100K–£500K → Regional Dir, >£500K → CFO | `product.yaml` new_org_defaults |
| Routing | Deterministic — no LLM for routing | Rule-based governance, not probabilistic |
| LLM use | Fallback only — explain routing rationale | Only if structured routing fails |
| Notification | Creates pending approval record in `evaluation_decisions` | Triggers dashboard alert for approver |
| Governance | RFP confirmation check before deciding | Prevents wrong-document decisions |
| Output model | `DecisionOutput` (Pydantic v2) | recommended_vendor, approval_tier, approver_role, evidence_citations |
| Critic check | `critic.py` — validates approval tier is valid, evidence_citations non-empty | HARD block if no citations |

---

## Agent 8 — Explanation Agent

**File:** `app/agents/explanation.py`
**Support file:** `app/output/pdf_report.py`
**Role:** Generates the final grounded report — every claim cited to a verbatim source.

| Component | Technology | Why |
|---|---|---|
| Input | All prior agent outputs (PostgreSQL facts + Pydantic models) | Full pipeline context |
| LLM | `call_llm()` — narrative generation | Synthesises structured data into readable report |
| Citation enforcement | Every claim in report body must reference a `source_chunk_id` | Critic checks citation completeness |
| Citation style | Configurable per org: inline / footnote (`org_settings.citation_style`) | Customer preference |
| Output tone | Configurable per org: formal / analytical / summary (`org_settings.output_tone`) | Enterprise formal vs. executive summary |
| Output language | Configurable per org (`org_settings.output_language`, default: en-GB) | Multilingual planned Q4 2026 |
| PDF generation | `app/output/pdf_report.py` | Structured PDF with tables, scores, citations |
| Output model | `ExplanationOutput` (Pydantic v2) | report_sections, citation_map, pdf_path |
| Critic check | `critic.py` — validates all claims have citations, grounding_quote present | HARD block if uncited claim detected |

---

## Agent 9 — Critic Agent

**File:** `app/agents/critic.py`
**Support files:** `app/core/retrieval_critic.py`, `app/core/extraction_critic.py`
**Role:** Validates the output of every other agent. The only agent that can block the pipeline.

| Component | Technology | Why |
|---|---|---|
| Trigger | After EVERY agent in the LangGraph topology | Cannot be bypassed by design |
| Flag types | HARD (pipeline block) / SOFT (warning + continue) / LOG (silent record) / ESCALATE (human review) | Graded response to different severity levels |
| Grounding check | Verbatim containment after whitespace normalisation | Core hallucination prevention |
| Confidence floor | `platform.yaml: retrieval_critic_confidence_floor: 0.6`, `extraction_critic_confidence_floor: 0.7` | Configurable minimum confidence |
| LLM use | None in main critic — rule-based checks | Deterministic guardrails, not probabilistic |
| LLM in sub-critics | `retrieval_critic.py` and `extraction_critic.py` use LLM for adequacy judgment | Semantic adequacy requires LLM |
| Observability | Every Critic flag logged to observability provider | Full audit trail of blocks and warnings |
| Override | HARD block can be overridden by human — creates AuditOverride record | Human in the loop preserved |
| Output model | `CriticOutput` (Pydantic v2) | flag_type, reason, agent_name, blocking |

---

## Infrastructure Summary

| Layer | Technology | Version | Notes |
|---|---|---|---|
| Orchestration | LangGraph | 1.1.10 | `from langgraph.graph import StateGraph, END` |
| Document parsing | LlamaIndex Core | 0.12.6 | HierarchicalNodeParser, SentenceWindowNodeParser |
| Vector store | Qdrant | 1.14.2 | `client.query_points()` (not deprecated `search()`) |
| Relational DB | PostgreSQL | 15+ | SQLAlchemy 2.0.40, psycopg2-binary 2.9.10 |
| LLM abstraction | `call_llm()` | custom | LangSmith `@traceable` wrapper |
| Reranker (default) | sentence-transformers CrossEncoder | 4.1.0 | `BAAI/bge-reranker-v2-m3` |
| API framework | FastAPI | 0.136.1 | Uvicorn 0.34.3 |
| Schema validation | Pydantic | 2.11.3 | `@field_validator` (v2 style throughout) |
| Observability | LangSmith 0.7.37 + LangFuse 4.5.1 | current | Swappable via OBSERVABILITY_PROVIDER |
| Burst compute | Modal | current | PDF CPU, embedding A10G, LLM A100-80GB |
| Frontend | Next.js | current | CEO dashboard, Procurement UI |
| Auth | JWT | PyJWT | org_id extracted server-side |
