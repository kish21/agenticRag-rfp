# Backlog

**Last reorganised:** 12 May 2026
**Owner:** Solo build, pre-first-customer
**Convention:** Items move between sections as state changes. P0 blocks production launch; P1 is required UX; P2 is architectural improvement; P3 is polish; P4 is "wait until a customer asks."

---

## ✅ COMPLETED — Done, dated, verified

| Date        | What                                                                                | How verified                                                             |
| ----------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 12 May 2026 | Four-layer config architecture (.env + platform.yaml + product.yaml + org_settings) | All 21 fields surface via API; 60s cache; audit table records changes    |
| 12 May 2026 | No-hardcode audit (`scripts/audit_hardcoded_values.py`)                             | Zero violations; planted-violation test confirms detection               |
| 12 May 2026 | Hybrid retrieval (dense + sparse + RRF fusion) wired into `run_retrieval_agent`     | Verified via search_hybrid call; `use_hybrid_search` flag now functional |
| 12 May 2026 | HyDE query expansion in retrieval                                                   | Active when `use_hyde=True`; template lives in platform.yaml             |
| 12 May 2026 | Retrieval critic with single-retry escalation                                       | 4 events in audit_log for run c1ea20a6; correctly retried ClearPath PI   |
| 12 May 2026 | Extraction critic for cert + insurance paths (mandatory)                            | Apex PI correctly retried; £10M Hiscox extracted on retry                |
| 12 May 2026 | P0.5 extraction adjacency bug (mandatory only) — closed                             | Apex shortlisted; ClearPath rejected with dispositive £3M evidence       |
| 12 May 2026 | Fixture test (`scripts/test_fixture_mandatory.py`)                                  | 4/4 known outcomes on Apex/ClearPath                                     |
| 12 May 2026 | Thread `run_id` through retrieval critic audit emission (P0.10)                     | retrieval_critic.verdict events now carry run_id; verified 69/69         |
| 12 May 2026 | Extend extraction critic to `fact_type="custom"` rows (P0.11)                       | Custom target loop added; 69/69, 4/4 fixture, 0 audit violations         |
| 12 May 2026 | Extend extraction critic to scoring criteria (P0.6)                                 | Scoring loop added using rubric_9_10 as quality benchmark; 69/69          |
| 12 May 2026 | Audit completeness CI check (P0.9) + extraction critic run_id threading             | AUDIT-CP01 added; extraction agent now threads run_id; 70/70              |
| 12 May 2026 | Log raw LLM response on critic fallback (P1.6)                                      | Both critics now log raw_response + exception type before defaulting      |
| 12 May 2026 | Approve page SLA countdown NaN bug (P0.14)                                          | Guard isNaN(ts); urgent from diff ms not parseInt(string); build clean    |
| 12 May 2026 | Vendor name at upload (P0.13)                                                        | Editable name field per vendor; vendor_names JSONB in DB; results display |
| 12 May 2026 | Re-evaluate button on results page (P0.15)                                           | Zero-score amber banner + re-evaluate POST endpoint; routes to progress   |
| 12 May 2026 | Chunk-level retrieval audit table (P0.8)                                             | retrieval_log table; log_retrieval() emits per call; run_id+criterion_id  |
| 12 May 2026 | Bulk extraction empty-fact retry (P0.7)                                              | Fixed skip on empty fact_list; targeted retry now fires for SLAs/pricing  |
| 12 May 2026 | Department pills route to filtered view (P1.5)                                       | Each pill → /dashboard/department/[name] with filtered run list           |
| 12 May 2026 | Weight editor auto-rebalance (P1.2)                                                  | New criterion defaults 5%; proportional rebalance of unlocked criteria    |
| 12 May 2026 | Override preview showing updated ranking (P1.3)                                      | After-override ranking preview card with projected shortlist              |
| 12 May 2026 | Side-by-side vendor comparison page (P1.1)                                           | /[runId]/compare with criteria rows × vendor columns; Compare button      |
| 12 May 2026 | Pydantic validation on synthesizer output (P1.12)                                    | SynthesisLLMResponse model validates LLM JSON before VendorNarrative      |
| 12 May 2026 | Recommendation text readable casing (P3.2)                                           | strongly_recommended → "Strongly recommended" in RecBadge                 |
| 12 May 2026 | Score band tooltips on results (P3.1)                                                | title= tooltip on score showing band meaning on hover                     |
| 12 May 2026 | Source badge legend visible by default (P3.3)                                        | SourceLegend component shown above criteria sections                      |

---

## 🔴 P0 — Blocks production launch

Things that prevent shipping to a paying customer.

### P0.12 — Multi-user visibility and role-based access

**Problem.** Today any user with a JWT for the same `org_id` can see any evaluation that org has run. RLS prevents cross-org leakage but not within-org. A procurement intern can see the CFO's confidential negotiations.

**Fix.** Role-based visibility model (owner / dept member / approver / CFO / auditor / admin) with Postgres RLS policies and an `access_audit_log` table.

**Effort.** 2-3 days.

---

## 🟡 P1 — Required UX

Things that make the product usable rather than demoable.

### P1.4 — Cancel running pipeline

**Problem.** No way to cancel mid-run; only option is wait for failure.

**Fix.** Cancel button sets status='cancelled'; active agents check flag at safe points and exit cleanly.

**Effort.** 1-2 days.

---

### P1.7 — Self-consistency voting for borderline compliance checks

**Problem.** Single LLM call on a borderline decision is brittle. Same question, three runs, different answers.

**Fix.** Run same compliance check 3 times, take majority. Apply only when confidence is borderline (e.g. 0.5-0.75) and the check is above approval threshold.

**Effort.** Half a day.

---

### P1.8 — Verification step after synthesis

**Problem.** Synthesis step generates narrative claims. Without a verification pass, the report can contain claims not strictly supported by retrieved context.

**Fix.** Second LLM call after synthesis checks every claim against retrieved chunks. Add as optional guardrail node before PDF report.

**Effort.** Half a day.

---

### P1.9 — Human feedback capture for AI score overrides

**Problem.** When evaluator overrides an AI score, the correction is lost. Future runs don't benefit.

**Fix.** Feedback UI in frontend; corrections flow back into few-shot example bank.

**Effort.** 1 day.

---

### P1.10 — Score drift detection in production

**Problem.** No alerting if average confidence drops week-over-week.

**Fix.** LangSmith has the data. Monitoring rule + Slack alert.

**Effort.** Half a day.

---

### P1.11 — Vendor Q&A — Conversational RAG for decision makers

**Problem.** Decision-makers see a rejection and either accept or override blind. They cannot interrogate the source documents.

**Fix.** Tab on the Evaluation Report page — "Ask about this vendor" — chat-style interface scoped to one vendor's Qdrant collection. Strict grounding: every answer cites exact quote + page number; never hallucinate evidence for overrides. Connects to the override flow: clicking "Override using this evidence" pre-fills the override form with the citation.

**Backend.** New endpoint `POST /api/evaluations/{run_id}/vendors/{vendor_id}/ask`. New Pydantic models: `Citation`, `VendorQARequest`, `VendorQAResponse`.

**Frontend.** Vendor selector dropdown; chat input; grounded answers with citation blockquotes; "Override using this evidence" button for rejected vendors.

**Effort.** 2-3 days.

**Test case.** Use Chemtura/YASH fixture: "What client references did YASH provide?" — should find John Deere, Stanley Works, Monsanto with page numbers.

### P1.12 — Real BM25 sparse retrieval ✅ DONE 2026-05-30 (PR feat/bm25-native-sparse)

**Resolution.** Replaced the MD5-hash TF approximation with real BM25: `fastembed`
`Qdrant/bm25` produces document/query sparse vectors (proper tokenizer, currency
+ alphanumerics preserved, length-normalised TF) and the Qdrant collection now
sets sparse `modifier=IDF`, so Qdrant applies corpus IDF server-side = full BM25.
`get_sparse_embedding()` split into asymmetric `get_sparse_document_embedding()` /
`get_sparse_query_embedding()`. `rank-bm25` removed (was unused). Backfill via
`tools/reindex_bm25.py`. Acceptance: `tests/test_sparse_retrieval_bm25.py` (3 tests,
green) — ISO 27001≠ISO 9001, £10M≠£1M, exact SLA clause > paraphrase.

> **Note vs. original plan:** Qdrant has no `modifier="bm25"` — the enum is
> `Modifier.IDF` / `Modifier.NONE`. Native BM25 = TF sparse vectors (fastembed)
> + `modifier=IDF` server-side, which required adding `fastembed` (approved).

**Problem (external reviewer, 2026-05-29).** `app/retrieval/pipeline.py:33-53` builds the "sparse vector" for hybrid retrieval by hashing words with MD5 into 100,000 buckets and storing raw normalised term-frequency. For procurement RFP evaluation this is **wrong in three specific ways:**

1. **MD5 → 100k buckets is a collision attack on procurement vocabulary.** Distinct certification IDs ("ISO 27001" vs "ISO 9001"), insurance terms, and SLA clauses can hash to the same bucket. Exact-clause search degrades to "approximate-clause-with-collisions search" — silently.
2. **TF without IDF over-weights common boilerplate.** Words like "vendor", "shall", "must" dominate the sparse vector. Rare-but-critical terms like specific certification numbers get washed out.
3. **No procurement-aware tokenizer.** "ISO 27001" splits into `iso` + `27001` with no preservation of the multi-token entity. Insurance amounts like "£10M" lose the currency symbol. The 3-character minimum drops "5G", "AI", "OK".

**Why it has shipped this long.** Hybrid retrieval combines this sparse layer with a real dense embedding (`text-embedding-3-large`, 3072-dim). The dense side carries most semantic load; the broken sparse layer hurts but doesn't dominate. The smoke test passes because dense retrieval finds the right chunks **most** of the time. The sparse layer's job is to be the safety net on disputed clauses, exact-figure assertions, and certification-ID checks — exactly the cases where dense embeddings have the most slack. So the layer is broken **where it matters most**.

**Fix.** Switch to Qdrant native BM25 sparse vectors (Qdrant 1.10+ supports server-side BM25 with proper tokenization). Three concrete steps:

1. **Update collection schema** in `app/retrieval/qdrant.py` to declare `sparse_vectors_config` with `modifier="bm25"` and a procurement-tuned tokenizer (preserves alphanumeric tokens, currency symbols, and multi-word phrases).
2. **Replace `get_sparse_embedding()`** in `app/retrieval/pipeline.py` — either delete it (let Qdrant generate the BM25 sparse from raw text server-side) or wire `rank_bm25.BM25Okapi` if we want client-side control. `rank-bm25==0.2.2` is already in `requirements.txt`; we are paying for it but not using it.
3. **Backfill** — re-ingest existing chunks so Qdrant builds the BM25 index from raw text. Add a one-shot script `tools/reindex_bm25.py`.

**Acceptance test.** Add `tests/test_sparse_retrieval_bm25.py`:
- Index fixture corpus containing two near-duplicate certifications differing only in numbers ("ISO 27001" vs "ISO 9001")
- Query for exact "ISO 27001"; assert top-1 result is the correct chunk; assert "ISO 9001" chunk is NOT in top-3
- Same test for insurance ("£10M public liability" vs "£1M public liability")
- Same test for SLA clauses

**Alternative (not recommended now).** SPLADE neural sparse — best quality but requires Modal A10G compute. Revisit once a real customer demands it.

**Effort.** Half a day for Qdrant native BM25; ~1 day if we also do the reindex script + the 3 acceptance tests. **Do BEFORE first real customer** — this is the difference between "demo-grade" and "procurement-grade" retrieval.

**Provenance.** External reviewer flagged this on 2026-05-29 after reviewing PRs #165 / #166. Reviewer's exact words: *"For procurement docs, exact clauses, ISO numbers, insurance terms, and SLA phrases matter. I would want real BM25/SPLADE-style sparse retrieval before production."*

---


## 🔵 P2 — Architectural improvements

Things that make the system more robust or capable. Interview-worthy "next steps."

### P2.0 — Phase 5 deferred benchmarks (D4 + E1)

Phase 5 (background ingestion) shipped with two exit criteria deferred to live integration:

- **D4** — `tools/smoke_test_graph.py` on a 5-vendor fixture, asserting that `deadline_processor.tick()` finishes the ingestion + extraction sub-graph in **<0.4× the equivalent sequential wall-clock**. Requires live OpenAI + Qdrant + real RFP fixture. Today only the orchestration smoke is unit-tested.
- **E1** — User-triggered `/api/v1/evaluate/start` AFTER background processing completes in **≤60 seconds** on the 5-vendor fixture (`agent_events.json` shows `ingestion.skipped` + `extraction.skipped` 5×). The short-circuit logic is unit-tested via mock; wall-clock proof requires the same live fixture.

**Fix.** Stand up a recurring integration job (Modal scheduled or GHA nightly with secrets) that runs both benchmarks on the standard fixture and records numbers in `tests/smoke_results/`. **Effort:** 1 day to wire + 1 day fixture curation.

### P2.0a — Phase 5 RFP/legacy-FK refactor

Phase 5 added an `rfps` table but left existing `vendor_documents`, `extracted_facts`, `evaluation_runs`, etc. with plain `rfp_id TEXT` columns (no FK to `rfps`). Intentional scope cap — full FK refactor was deferred to keep PR-A small. **Fix.** Add FKs in a follow-up migration, backfill orphan `rfp_id` strings into the `rfps` table (with `title='<unknown — legacy>'`), then enforce FK. **Effort:** Half a day if no orphans exist; up to 2 days with backfill.

### P2.0b — Phase 3 live cost-savings benchmark (criterion 3.17)

Phase 3 (LLM response cache) shipped with one exit criterion deferred to live integration: **3.17** — second smoke run on the standard fixture with cache hot must show wall-clock < 60s (vs ~5 min uncached), ≥95% cache hit rate, and $0 LLM spend (verified via `summary.json`). Today only unit-level and concurrency tests cover the cache. The 3.17 benchmark requires live OpenAI calls + a populated cache. **Fix.** Run `tools/smoke_test_graph.py` once cold to populate the cache, then a second time and assert `summary.json.cache.hit_rate >= 0.95`. Add a `--assert-cache-hit-rate=0.95` flag to `tools/smoke_test_graph.py` for CI-friendliness. **Effort:** Half a day.

### P2.0c — Phase 2c finish critic-as-controller

Phase 2 plan promised all 9 agents under the Critic-as-controller pattern (retry-with-feedback, 3-way routing: continue / retry / block). Today only **Explanation** has the full pattern. The other 7 agents (Planner, Ingestion, Retrieval-partial, Extraction, Evaluation, Comparator, Decision) still run the critic inline and can only block. **Fix.** Promote Critic-as-controller to dedicated LangGraph nodes for Extraction + Evaluation first (highest leverage per the original Phase 2 plan); Planner / Ingestion / Comparator / Decision remain deferred as "reliable enough in smoke runs." **Effort:** 1 day for Extraction + Evaluation.

### P2.1 — Replace TF-IDF sparse with proper BM25 (PROMOTED TO P1.12 below — 2026-05-29)

Original P2 entry: Switch to Qdrant's native BM25 sparse vectors. Re-ingestion required. **Promoted** to P1.12 after external reviewer flagged this as a procurement-grade correctness risk, not a polish item. See P1.12 for the full reasoning + plan.

### P2.2 — Retrieval critic LLM cache

**Fix.** Hash inputs into cache key; Redis or Postgres lookup before LLM call; 7-day TTL. **Effort:** Half a day.

### P2.3 — Hybrid search for Balanced tier

Decision needed: enable by default (raises cost ~3.5x) vs. keep as escalation only. **Effort:** 10 min config change. Wait for production data.

### P2.4 — Expanded fixture suite

Add fixtures for construction, healthcare, public sector, software. **Effort:** 1 day per fixture.

### P2.5 — Critic retry cost analysis dashboard

First-pass vs retry rate over time, by criterion type. **Effort:** 1 day.

### P2.6 — Confidence-tier-aware UX

Banner showing current tier and cost-per-evaluation; cost history. **Effort:** 1-2 days.

### P2.7 — Prompt versioning

`prompt_version` column in decisions table; emit version with every LLM call. **Effort:** Half a day.

### P2.8 — OCR for scanned PDFs

Tesseract integration in ingestion path. Detect scan-only pages; OCR them. **Effort:** 1 day.

### P2.9 — Document versioning

Version vendor documents; keep previous versions queryable. **Effort:** 1 day.

### P2.10 — Confidence calibration

Empirically calibrate confidence scores against ground truth dataset (P3.6 prerequisite). **Effort:** 2 days.

### P2.11 — Context compression

`ContextualCompressionRetriever` extracts only relevant sentences from chunks. **Effort:** Half a day.

### P2.12 — Lost-in-the-middle handling

Sort retrieved chunks by importance; place most important first and last. **Effort:** 2 hours.

### P2.13 — Contextual chunk headers

Prepend each chunk with parent section summary. One extra LLM call per chunk at ingestion. **Effort:** 1 day.

---

## ⚪ P3 — Polish

| ID    | What                                                                                  | Effort     |
| ----- | ------------------------------------------------------------------------------------- | ---------- |
| P3.4  | Dashboard search and filter (vendor, RFP, date, status)                               | Half a day |
| P3.5  | Estimated time remaining on progress page                                             | Half a day |
| P3.6  | Ground truth evaluation dataset (first customer, 20 vendors)                          | Ongoing    |
| P3.7  | A/B prompt testing — requires P3.6                                                    | 1 day      |
| P3.8  | Export with criterion-level detail + grounding quotes                                 | Half a day |
| P3.9  | Save as draft on upload page                                                          | Half a day |
| P3.10 | Retry failed pipeline from progress page (from blocked agent, not scratch)            | 1 day      |
| P3.11 | Approval SLA checker background job + Slack reminder                                  | Half a day |
| P3.12 | Retrieval quality monitoring in production (weekly scheduled test)                    | Half a day |

---

## 🟣 P4 — Future architecture

Only build when a customer asks.

| ID   | What                                                                       |
| ---- | -------------------------------------------------------------------------- |
| P4.1 | Cross-encoder reranker swap (Cohere → BGE) once cost matters               |
| P4.2 | Multi-language support (EN-GB only now; add on first non-English customer) |
| P4.3 | Cross-evaluation memory (vendor history across multiple RFPs)              |
| P4.4 | Slack/email/Teams approval notifications                                   |
| P4.5 | Long-context experimental mode for small RFP sets (<200 pages)             |
| P4.6 | SaaS billing system (Stripe integration, per-org usage metering)           |
| P4.7 | Executive dashboard (CEO/CFO view across departments)                      |
| P4.8 | Chunk overlap strategy (sentence-boundary if needed)                       |
| P4.9 | Hierarchical chunking (summary + detail per section)                       |

---

## ❌ REJECTED — Considered and not building

| Date     | What                                | Why rejected                                                                   |
| -------- | ----------------------------------- | ------------------------------------------------------------------------------ |
| Apr 2026 | Fine-tuning models                  | Too expensive for v1; few-shot achieves comparable. Revisit after 1000+ evals. |
| Apr 2026 | Image/audio ingestion               | Out of scope; vendor responses are text.                                       |
| Apr 2026 | Knowledge graph layer               | Doesn't solve any observed failure mode.                                       |
| Apr 2026 | Per-customer LLM provider switching | Operational complexity without clear benefit.                                  |
| Apr 2026 | Real-time collaborative editing     | Procurement is sequential, not collaborative writing.                          |
| Apr 2026 | Mobile app                          | Procurement is desktop work.                                                   |

---

## How to use this document

**Don't move items by date.** Move them by state. Completed → COMPLETED section with the date and verification method. In progress → IN FLIGHT with who's working on it. Active backlog → tiered by P-level.

**Re-tier monthly.** A P2 today may become P0 the moment a customer hits the underlying gap. A P0 may slide to P1 if the workaround turns out acceptable.

**Each item has problem / fix / effort.** If you can't write those three, it's not an item — it's an idea. Ideas live in a separate "ideas to evaluate" list, not in the backlog.

**The COMPLETED section is your interview story.** When asked _"what have you actually built?"_ — read down the COMPLETED table. Each row is a defensible claim with evidence.

**The P0 section is your honest answer to _"what's not done yet?"_** Not "everything is done" — "here are the genuine production blockers I haven't shipped yet and roughly how long each would take." That's senior thinking.
