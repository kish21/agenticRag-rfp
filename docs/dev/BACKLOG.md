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

### P0.16 — Tenant isolation: PostgreSQL RLS is currently INERT (external audit 2026-05-30)

**Provenance.** External auditor flagged tenant-isolation issues (7 prompts, see end of this item). Verified against the code 2026-05-30 — the findings are real, and the root cause is **deeper than the audit states**. ⚠️ Note: P0.12 below claims "RLS prevents cross-org leakage" — that claim is **FALSE today** (see below); fix this item first.

**Verdict (verified): RLS enforces NOTHING right now, for TWO independent reasons.**

1. **The RLS context is never set on query connections.** [app/api/middleware.py:54-59](app/api/middleware.py#L54-L59) does `with engine.connect() as conn: conn.execute("SET LOCAL app.current_org_id=…"); conn.commit()`. `SET LOCAL` is **transaction-scoped**, so `commit()` discards it immediately, and then the connection closes and returns to the pool. Route handlers open a *different* connection. → the context is a **guaranteed no-op** (worse than the audit's "separate connection" framing).
2. **The app role bypasses RLS entirely.** `schema.sql` has `ENABLE ROW LEVEL SECURITY` on 22 tables but **`FORCE ROW LEVEL SECURITY` on 0**. The app connects as `platformuser` (the Postgres container **superuser + table owner**). In PostgreSQL, **RLS does not apply to the table owner/superuser unless `FORCE ROW LEVEL SECURITY` is set.** → even with the context fixed, RLS would still be bypassed. **The audit's 7 prompts do not mention this — it is the single most important fix.**

**Naming split (also confirmed).** Everything uses `app.current_org_id` EXCEPT `org_settings`, which uses `app.org_id`:
- code: [app/api/org_settings_routes.py:49](app/api/org_settings_routes.py#L49), [app/domain/org_settings.py:77](app/domain/org_settings.py#L77),[110](app/domain/org_settings.py#L110)
- RLS policies: [app/db/schema.sql:571](app/db/schema.sql#L571),[581](app/db/schema.sql#L581)

**Honest severity.** Likely **no active cross-org leak today** — isolation is actually carried by **application-level `WHERE org_id` filters** (`_db_get_run`, `require_run_access`, Phase 9 visibility). The app works *because* RLS is bypassed and the app filters do the real work. BUT: (a) the README/security claim "isolation enforced at JWT + RLS + Qdrant" is **false** for the RLS layer — a diligence reviewer will catch it; (b) there is **no DB backstop** — one forgotten `WHERE org_id` in any future query leaks tenants silently. Not a fire today; a real defense-in-depth hole + a false security claim.

**Action plan (TEST-FIRST — prove the gap, then fix, then prove the fix):**

1. **Cross-org isolation tests that FAIL today** (prove RLS is inert):
   - **DB/RLS level:** connect as a *non-owner* role with `app.current_org_id` = org A; assert a raw `SELECT` cannot see org B rows in `evaluation_runs`, `rfps`, `vendor_documents`, `org_settings`, `org_settings_audit`, extracted_* tables. (These FAIL now → proves the hole.)
   - **API level:** org A token → 404/403 reading/updating/deleting org B's run / RFP / vendor docs / settings / override / export / admin-attribution (audit Prompts 4–6 routes).
   - Missing tenant context → zero protected rows.
2. **Make RLS real:**
   - `FORCE ROW LEVEL SECURITY` on all 22 protected tables (Alembic migration). AND/OR run the app as a dedicated **non-owner** DB role (`platform_app`) that only RLS governs. (FORCE is the minimum; non-owner role is belt-and-suspenders.)
   - Move `SET LOCAL app.current_org_id` OUT of the throwaway-connection middleware and INTO the **actual DB session/dependency** used by handlers (so it's on the same connection, inside the same transaction as the query, NOT committed away). Fix/remove the misleading middleware + its comment.
   - Standardize `app.org_id` → `app.current_org_id` everywhere (org_settings code + schema.sql:571/581 policies); Alembic migration for the policy change. No remaining runtime `app.org_id`.
3. **Vendor + run ownership (Prompts 5–6):** every vendor access tied to current org + RFP/run (not vendor_id alone); run_id never trusted alone. Tests for invite/attribute/results/override/admin endpoints.
4. **Re-run step-1 tests → now PASS.** Then write the **honest** enterprise-reviewer summary (Prompt 7) — only after tests prove RLS enforces.

**Acceptance criteria:** (a) `FORCE ROW LEVEL SECURITY` on all protected tables; (b) RLS context set on the same connection as queries (verified by a test); (c) zero runtime `app.org_id`; (d) DB-level + API-level cross-org read/write tests green; (e) README/PERFORMANCE security claims updated to match reality; (f) reviewer summary written and true.

**Effort.** ~2–3 days (DB role + migrations + session refactor + comprehensive tests). **Do before any enterprise security review / due diligence.**

<details><summary>External auditor's 7 prompts (preserved verbatim)</summary>

1. **Move RLS context into actual DB session** — `SET LOCAL app.current_org_id` belongs in the DB dependency/session used by handlers, not middleware on a separate connection; every authenticated request's connection has org context before queries; keep public routes working; tests: org A can't read/update/delete org B rows; context on the same connection as the query.
2. **Standardize on `app.current_org_id`** — replace all `app.org_id`; update `org_settings`/`org_settings_audit` policies + app code; Alembic if needed; tests: org A settings/audit not visible to org B; no runtime `app.org_id` remains.
3. **Remove `app.org_id` from org_settings policies** — `org_settings` + `org_settings_audit` use `current_setting('app.current_org_id', true)`; update `app/domain/org_settings.py` + routes; Alembic; tests: read own / not others' / can't update others' / audit isolated.
4. **Cross-org read/write isolation tests** — two orgs + tokens + data; org A can't read/update/delete org B evaluation runs / RFPs / vendor docs / settings; missing context → no rows; both API (403/404) and DB/RLS level.
5. **Vendor ownership tests** — org A can't access org B vendor docs / invite-update-attribute on org B's RFP; vendor_id must belong to current RFP; run only uses vendor_ids of that org/RFP; cross-org guessing → 404. Endpoints: invite, eval create/confirm, results/detail, override, admin attribution.
6. **Run ownership tests** — org A can't view setup/stream/results/export/override/delete org B's run; consistent 404/403. Routes: `/evaluate/{run_id}/{setup,confirm,status,results,export,override}` + delete/retry.
7. **Enterprise reviewer summary** — concise technical note: isolation model, org_id from JWT, how `app.current_org_id` is set, how RLS uses it, route-level org/run/vendor ownership checks, what tests prove, what happens on cross-org access, remaining limitations. Tone for a security-conscious buyer / due-diligence reviewer.

</details>

---

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
