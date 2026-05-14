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

---


## 🔵 P2 — Architectural improvements

Things that make the system more robust or capable. Interview-worthy "next steps."

### P2.1 — Replace TF-IDF sparse with proper BM25

**Fix.** Switch to Qdrant's native BM25 sparse vectors. Re-ingestion required. **Effort:** Half a day including backfill.

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
