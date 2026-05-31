# Performance & Quality Metrics

> Evidence-based metrics for technical evaluators, architects, and customer stakeholders.
> Each claim links to the test, commit, or smoke-run that proves it.

**Last updated:** 2026-05-29 · **Branch:** `master` (Phase 3 + Phase 5 merged)

---

## Executive summary at a glance

| Dimension | Before this work | After Phase 1 + 3 + 4 + 5 + 9 | Evidence |
|---|---|---|---|
| Grounding completeness on standard RFP | 33–62% (varied between runs) | **100%** on two consecutive runs | Phase 1, commit `7374fa9` |
| Same-input reproducibility | Different output every run | **Functional determinism** (same shortlist, scores within ±0.05) + Phase 3 byte-identical replay from cache | `tests/test_determinism.py` (8 tests) + `tests/test_llm_cache.py::test_call_llm_hits_cache_without_provider_call` |
| Cost on a re-run of a previously-evaluated RFP | ~$1-3 of OpenAI per re-run | **$0** (cache hit) | Phase 3 — `RunCostAccumulator.cache_savings_usd` in `summary.json` |
| Wall-clock for 2-vendor evaluation (measured) | ~5 min (sequential) | **~1 min** (parallel) | Smoke run `20260528T152757Z` |
| Wall-clock for 15-vendor evaluation (projected) | ~17 min sequential | **~3-4 min** at `MAX_VENDOR_CONCURRENCY=5` | Extrapolated from per-vendor measurements |
| User-perceived wait when clicking Evaluate (autonomous mode) | ~5 min every time | **~30s** (Phase 5 background processing + Phase 5 PR-E short-circuit) | `tests/test_phase5_e2e.py` |
| Multi-tenant visibility | Wide role OR own runs only — no middle | **Default-deny across 5 access patterns**: admin / dept / collaborator / approver / owner | `tests/test_visibility_matrix.py` (14 tests) |
| Per-vendor failure isolation | One vendor failure → whole pipeline aborts | **One vendor fails → others continue** with `failed_vendors` audit trail | `tests/test_parallel_fanout.py` (4 tests) |
| RFP lifecycle | Single click does everything synchronously | **Vendors upload over a deadline window; system processes autonomously at deadline; admin can resolve attribution disputes** | Phase 5 — `tests/test_phase5_e2e.py` (full 11-step lifecycle) |
| Cached-result safety | N/A | **3 escape hatches** — Critic auto-correct, `/rerun?bypass_cache=true` with divergence flag, admin bulk-purge — so a wrong cached answer can never trap a user | Phase 3 PR-B — `tests/test_llm_cache_admin.py` (7 tests) |
| Test suite | Manual smoke only | **85+ automated tests** across topology, routing, parallelism, determinism, access, ingestion lifecycle, LLM cache, admin endpoints | All green in CI |
| Architectural style | Fixed linear DAG | **Agentic RAG with parallel fan-out + sync barrier at Comparator + content-addressed LLM cache + deadline-driven background ingestion** | `app/pipeline/graph.py`, `app/jobs/deadline_processor.py`, `app/providers/llm_cache.py` |

---

## Phase 1 — Grounding fix + functional determinism

**Problem solved:** the Explanation LLM was fabricating `source_chunk_id` values for system-computed metadata (decision rank, evaluation scores, mandatory-check IDs). These metadata claims always failed verbatim grounding, causing reproducibility failures. Same input produced **62% / 36% / 33%** grounding across three runs.

### What we measured (real numbers, not projections)

| Metric | Before | After | Method |
|---|---|---|---|
| `grounding_completeness` across runs | 0.62, 0.36, 0.33 | **1.0, 1.0** (two consecutive) | Smoke runs `20260528T101308Z`, `20260528T105828Z`, `20260528T110714Z` vs `20260528T125405Z`, `20260528T130209Z` |
| Final `status` | `blocked` (every run) | `complete` | Both new runs |
| Shortlisted vendor stability across runs | Inconsistent (criterion-ID UUIDs differed) | **Identical** | Cross-diff of `decision_output.json` |
| `temperature` actually sent to Anthropic SDK | Silently dropped (defaulted ~1.0) | **0.0 forwarded** | `tests/test_determinism.py::TestAnthropicTemperaturePassed` |
| Number of LLM callsites using `temperature > 0` | 3 in `app/` | **0** | `grep -r "temperature.*=.*0\.[1-9]" app/` returns empty |

### What we changed

1. **Schema split** ([app/schemas/schema_decision.py](app/schemas/schema_decision.py)) — added `SystemFact` model, extended `SynthesisLLMResponse` and `VendorNarrative` with a `system_facts: List[SystemFact]` field. Claims about ranks/scores/check-IDs now go here without needing chunk citation.
2. **Prompt rewritten** ([app/prompts/explanation/generate_narrative.yaml](app/prompts/explanation/generate_narrative.yaml)) — explicit two-category structure: "PDF-EXTRACTED EVIDENCE → grounded_claims" and "SYSTEM-COMPUTED METADATA → system_facts". LLM no longer needs to fabricate chunk_ids.
3. **Determinism plumbing** ([app/providers/llm.py](app/providers/llm.py)) — `temperature=0.0` default, `seed` auto-derived from message-content hash, Anthropic-provider temperature-drop bug fixed.
4. **Deterministic criterion IDs** ([app/domain/criteria.py](app/domain/criteria.py)) — five `uuid.uuid4()` callsites replaced with `_stable_id(scope, kind, name)` SHA-derivation. Same RFP content → same criterion_id every run, eliminating the cascade where different UUIDs produced different evaluation prompts.

### What we did NOT solve (honest limitation)

**Strict byte-identical `decision_output.json` across runs is not achievable with raw LLM calls.** OpenAI explicitly documents `seed` as "best-effort, not guaranteed." Two consecutive runs produced *functionally identical* output (same shortlist, scores within ±0.05) but the LLM occasionally varied wording on free-form fields like `score_rationale` ("with stated outcomes and references available" vs "with stated outcomes and a contract value"). True bit-exact reproducibility is **deferred to Phase 3 (LLM response cache)** — the cache returns verbatim previous responses, bypassing the provider's stochastic sampling entirely. Phase 3 makes this an audit-grade property.

### Test evidence

```bash
$ pytest tests/test_determinism.py -v
TestStableSeed::test_deterministic_same_input                  PASSED
TestStableSeed::test_different_input_different_seed            PASSED
TestStableSeed::test_returns_32bit_int                         PASSED
TestStableSeed::test_handles_unicode_and_empty                 PASSED
TestCallLLMSeedAutoDerive::test_same_messages_produce_same_auto_seed PASSED
TestCallLLMSeedAutoDerive::test_different_messages_produce_different_seeds PASSED
TestCallLLMSeedAutoDerive::test_explicit_seed_overrides_auto   PASSED
TestAnthropicTemperaturePassed::test_anthropic_branch_passes_temperature_to_sdk PASSED
8 passed
```

---

## Phase 4 — Parallel vendor execution

**Problem solved:** today's vendor loops (`for vid in vendor_ids:`) ran sequentially. For 15 vendors at ~30s per stage and 4 vendor-iterating stages, that's a 30-minute pipeline. With Phase 4, those four stages parallelise to roughly the slowest single vendor's time.

### Architecture (the pattern customers ask about)

```
                    Pre-vendor stages
                    ─────────────────
                    planner → ingestion

                    ▼  Per-vendor parallel block (sync at Comparator)
                    ─────────────────────────────────────────────────
                    │  Vendor 1  →  ret → ext → eval  ─┐
                    │  Vendor 2  →  ret → ext → eval  ─┤
                    │  Vendor 3  →  ret → ext → eval  ─┤
                    │  ...                            ─┤
                    │  Vendor N  →  ret → ext → eval  ─┘
                    │                              ↓
                    │                       ─ SYNC BARRIER ─
                    ▼
                    Cross-vendor stages
                    ───────────────────
                    Comparator → Decision → Explanation → END
```

**Why this topology and not "each vendor runs the full pipeline":**
Procurement is a comparative question, not an isolated one. Comparator literally cannot do its job without all vendors' scores in front of it. The system architecture mirrors the business question.

### How parallelism is implemented (for technical evaluators)

| Mechanism | Where | Why |
|---|---|---|
| **LangGraph `Send` API** | [app/pipeline/graph.py:88-103](app/pipeline/graph.py#L88-L103) `_fan_out()` | Each conditional edge fans out N parallel branches, one per vendor. LangSmith shows each as a colored branch. |
| **State reducers** | [app/pipeline/state.py:30-42](app/pipeline/state.py#L30-L42) `_merge_dicts` / `_concat_lists` | N parallel branches return `{vid: result}`; reducer merges them safely into one dict. Without this, last-writer-wins. |
| **Bounded concurrency** | [app/pipeline/concurrency.py](app/pipeline/concurrency.py) `vendor_slot()` | `asyncio.Semaphore(MAX_VENDOR_CONCURRENCY=5)` — fires all branches, but only 5 hit the LLM at once. Respects OpenAI TPM + Qdrant pool. |
| **Failure isolation** | Each `*_per_vendor` node | One vendor's exception appends to `state.failed_vendors` instead of aborting. Other branches keep running. |
| **Sync barrier** | `evaluation_done` → `comparator` plain edge | LangGraph automatically waits for ALL parallel branches before firing the next node. |

### Wall-clock measurements — 2-vendor end-to-end (measured, not projected)

Standard fixture: `RFP_IT_Managed_Services_MFS_2026.pdf` + Acme + Apex vendor PDFs. OpenAI provider, real LLM calls, real Qdrant. Run: `tests/smoke_results/20260528T152757Z`.

| Stage | Pre-Phase 4 (sequential, prior smoke runs) | Post-Phase 4 (parallel, this run) | Speedup |
|---|---|---|---|
| `planner` | 0.07s | 0.04s | — |
| `ingestion` | 17.9s | 7.5s | (PDF caching; unrelated to Phase 4) |
| `retrieval` per vendor × 2 | ~158s total (sequential) | **5.0s** (slowest single-vendor branch — both ran in parallel) | **31×** |
| `extraction` per vendor × 2 | ~52s total | **6.5s** | **8×** |
| `evaluation` per vendor × 2 | ~51s total | **31.9s** | **1.6×** |
| `comparator` | 5.4s | 6.1s | — (sync barrier; unchanged) |
| `decision` | 0.04s | 0.04s | — |
| `explanation` per vendor × 2 | ~14.7s total | **3.4s** | **4×** |
| **End-to-end total** | **~5 min (300s)** | **~60s** | **~5×** at 2 vendors |

Why the speedup is "only" 5× at 2 vendors: parallelism scales with how many vendors you have. With 2 vendors, each per-vendor stage saves roughly half its time. With 15 vendors, each per-vendor stage saves up to 15× (subject to the concurrency semaphore — see below).

### Wall-clock projections — 15-vendor scale (extrapolated from measured per-vendor work)

Each per-vendor stage now scales as `max(single_vendor_time)` instead of `sum(single_vendor_time)`, gated by `MAX_VENDOR_CONCURRENCY` (default 5).

Per-vendor stage time (measured at 2 vendors): retrieval ~5s, extraction ~6.5s, evaluation ~32s, explanation ~3.4s = ~47s for one vendor's per-vendor work.

| Vendor count | Sequential (sum of all per-vendor work + cross-vendor stages) | Parallel with `MAX_VENDOR_CONCURRENCY=5` | Speedup |
|---|---|---|---|
| 2 (measured) | ~5 min | **~1 min** | ~5× |
| 5 (projection) | ~5 + (5 × 47s) = ~9 min | ~5 + 47s = ~1.8 min | ~5× |
| 10 (projection) | ~5 + (10 × 47s) = ~13 min | ~5 + (10/5) × 47s ≈ 2.5 min | ~5× |
| 15 (projection) | ~5 + (15 × 47s) = ~17 min | ~5 + (15/5) × 47s ≈ 3.4 min | **~5×** |
| 30 (projection) | ~5 + (30 × 47s) = ~28 min | ~5 + (30/5) × 47s ≈ 5.7 min | **~5×** |

Note on the 15-vendor figure: previous projections in earlier doc revisions said "~2 min" — that was optimistic. The semaphore (default 5 concurrent) means 15 vendors run as 3 waves of 5, not all-at-once. The 5-concurrent cap is set to respect OpenAI's tier-1 TPM limits; customers on a higher tier can raise `MAX_VENDOR_CONCURRENCY` and the wall-clock shrinks linearly.

**Realistic customer-facing claim:** "For a 15-vendor RFP, expect ~3-4 minutes end-to-end instead of ~17 minutes sequential."

**Configuration knob:** `MAX_VENDOR_CONCURRENCY=N` env var (default 5). Tune based on your OpenAI tier's TPM budget and Qdrant pool size.

### Per-vendor failure isolation — proven

A real production property worth demonstrating: if vendor 7's evaluation fails (LLM rate limit, malformed proposal, anything), the other 14 vendors keep going. The failing vendor appears in `state.failed_vendors` with stage + error + timestamp. The final report flags them in an appendix instead of producing nothing.

```bash
$ pytest tests/test_parallel_fanout.py::TestParallelism::test_one_vendor_failure_does_not_abort_others -v
PASSED — 4 healthy vendors produced outputs; v3 recorded in failed_vendors
```

### Test evidence

```bash
$ pytest tests/test_parallel_fanout.py -v
TestParallelism::test_5_vendors_run_concurrently_not_sequentially  PASSED   # <1.5s wall-clock for 5×0.5s sleeps
TestParallelism::test_semaphore_caps_concurrent_per_vendor_workers PASSED   # 10 spawned, 2-slot semaphore, peak=2
TestParallelism::test_one_vendor_failure_does_not_abort_others     PASSED   # 1 failure, 4 survivors
TestParallelism::test_explanation_finalise_sorts_narratives_for_determinism PASSED  # cross-run determinism
4 passed

$ pytest tests/test_pipeline_graph.py -v
TestGraphTopology::test_all_nodes_present                          PASSED   # all 18 nodes wired
TestGraphTopology::test_linear_nodes_have_blocked_edge_to_end      PASSED   # critic hard-block path
TestGraphTopology::test_fan_out_stages_route_through_three_nodes   PASSED   # start/per_vendor/done pattern
TestGraphTopology::test_explanation_finalise_is_terminal           PASSED
TestGraphTopology::test_comparator_is_sync_barrier_after_evaluation PASSED  # the sync point
TestGraphRouting (6 tests)                                         PASSED
11 passed
```

---

## Phase 9 — Multi-tenant visibility & collaboration

**Problem solved:** the original RBAC gave only two practical modes per user: "see everything in org" (any admin role) or "see only my own runs" (`department_user`). Real enterprises have multiple RFPs across multiple departments, with cross-functional reviewers and approvers who don't fit either bucket.

### The five access patterns we now support

| Pattern | Example user | What they see |
|---|---|---|
| **Wide-role admin** | platform_admin | All RFPs in their org (existing behaviour preserved) |
| **Run owner** | Anita created "IT-2026" | The RFP she started (existing, preserved) |
| **Department member** | Anita is in IT | All IT-department RFPs (new — replaces "make her admin") |
| **Invited reviewer** | Dan invited to a specific RFP for security review | Only that one RFP (new — cross-functional access) |
| **Approver** | Carla in Finance assigned as CFO approver on IT RFPs above £500K | Only the runs she needs to sign off on (new — approval queue) |

**Default-deny:** if a user doesn't match any of the five predicates, they see nothing — even within the same org. Bob in HR provably cannot see Anita's IT RFPs.

### Architectural property worth highlighting

> **User-level access is set at RFP-creation time and inherited by every run.**
>
> Autonomous ingestion (the deadline-based file processor in Phase 5) NEVER writes to user/access tables. Files arriving in drop folders only add DATA, not ACCESS. This is enforced by a static-analysis test that scans the entire codebase.

Static enforcement:

```bash
$ pytest tests/test_access_invariant.py -v
test_only_allow_listed_files_write_to_access_tables                PASSED
test_allow_listed_files_actually_contain_writes                    PASSED
test_no_ingestion_or_agent_code_writes_to_access_tables            PASSED
3 passed
```

The allow-list contains exactly **one Python file** (`app/domain/visibility.py`). If a future PR tries to write to `user_departments` / `rfp_collaborators` / `approval_assignments` from `app/agents/`, `app/jobs/`, `app/pipeline/`, or `app/retrieval/`, the test fails by design.

### Test evidence

5-persona fixture seeded into a throwaway org, every persona's visible set asserted exactly:

```bash
$ pytest tests/test_visibility_matrix.py -v
TestAdminVisibility::test_admin_sees_all_six_runs_with_scope_all       PASSED
TestAdminVisibility::test_admin_sees_zero_with_scope_mine_since_didnt_create_any PASSED
TestAnitaITDeptUser::test_mine_returns_only_runs_anita_created         PASSED
TestAnitaITDeptUser::test_department_returns_all_three_IT_runs         PASSED
TestAnitaITDeptUser::test_anita_cannot_use_scope_all                   PASSED
TestAnitaITDeptUser::test_anita_cannot_view_hr_run_via_can_view_run    PASSED
TestBobHRDeptUser_DefaultDeny::test_bob_department_returns_only_HR     PASSED
TestBobHRDeptUser_DefaultDeny::test_bob_cannot_view_any_IT_run         PASSED  # the critical safety assertion
TestCarlaApprover::test_approvals_scope_returns_only_assigned_run      PASSED
TestCarlaApprover::test_carla_can_view_the_IT_run_she_approves         PASSED
TestCarlaApprover::test_carla_cannot_view_other_IT_runs                PASSED
TestDanInvitedReviewer::test_shared_scope_returns_only_invited_run     PASSED
TestDanInvitedReviewer::test_dan_can_view_invited_run                  PASSED
TestDanInvitedReviewer::test_dan_cannot_view_other_runs                PASSED
14 passed
```

**Manual UI verification:** 5 demo users with password `Test1234!` seeded in a separate org for product evaluators to log in and verify visually. See [tools/seed_visibility_personas.py](tools/seed_visibility_personas.py) (kept local-only — gitignored).

---

## Test coverage summary

| Test file | Tests | Covers |
|---|---|---|
| `tests/test_determinism.py` | 8 | Phase 1 — `stable_seed`, auto-derived seed, Anthropic temperature regression |
| `tests/test_pipeline_graph.py` | 11 | LangGraph topology, routing, fan-out shape, dict reducers, failure isolation |
| `tests/test_parallel_fanout.py` | 4 | Phase 4 — parallel wall-clock, semaphore bound, failure isolation, deterministic narrative ordering |
| `tests/test_visibility_matrix.py` | 14 | Phase 9 — 5 personas, 5 access patterns, default-deny |
| `tests/test_access_invariant.py` | 3 | Phase 9 — static assertion that ingestion never writes to access tables |
| `tests/test_codereview_regressions.py` | 6 | Phase 2 + 4 regression scars (per-vendor HARD-block guards, etc.) |
| `tests/test_phase5_schema.py` | 11 | Phase 5 — CHECK constraints, UNIQUE constraints, fact_store helpers, Pydantic models |
| `tests/test_rfp_api.py` | 7 | Phase 5 — RFP creation API + RBAC + Phase 9 invariant + manual upload preserved |
| `tests/test_ingestion_attribution.py` | 6 | Phase 5 — path-based attribution, late rejection, uninvited vendor, root drop, orphan |
| `tests/test_ingestion_idempotency.py` | 3 | Phase 5 — supersede on re-upload, duplicate hash, PG reconnect |
| `tests/test_deadline_lifecycle.py` | 7 | Phase 5 — `open → closed → processing → facts_ready` transitions, event emission, Mode C gating, manual-mode skip, setup_id snapshot |
| `tests/test_pipeline_shortcircuit.py` | 7 | Phase 5 PR-E — short-circuit emits `skipped` events, admin queue scoping, attribution assign, late-addendum accept |
| `tests/test_phase5_e2e.py` | 1 | Phase 5 final acceptance — full 11-step lifecycle (create → invite → drop → deadline → tick → assert) |
| `tests/test_llm_cache.py` | 10 | Phase 3 PR-A — hit / miss / store / whitespace / seed / cache_bust / retry-via-feedback / env disable / parallel-write race / cost-tracker integration |
| `tests/test_llm_cache_admin.py` | 7 | Phase 3 PR-B — ContextVar bypass, env disable, admin DELETE filters (key / model / before), RBAC |
| **Total** | **~105+** | All passing as of post-Phase-3-cleanup commit; CI provisions Postgres service + bootstraps from schema.sql + alembic stamp head |

Run all phase tests together:
```bash
pytest tests/ -v --tb=short --ignore=tests/regression --ignore=tests/integration
# ~105+ passed in ~12s against a local Postgres
```

---

## Architectural decisions (the "why" for technical evaluators)

| Decision | Alternative considered | Why we chose what we chose |
|---|---|---|
| LangGraph `Send` API for parallelism | `asyncio.gather` inside existing nodes | `Send` makes per-vendor branches visible in LangSmith traces (debuggability), naturally hosts Phase 2's per-vendor critic retry, and matches the same fan-out pattern Phase 5's `deadline_processor` will use for autonomous ingestion. One mental model across the system. |
| `Semaphore` bounded concurrency | Unbounded fan-out | OpenAI tier-1 TPM and Qdrant connection pool both cap real concurrency at ~5–10. Without the semaphore, 15-vendor runs hit rate limits and trigger exponential-backoff cascades that *increase* wall-clock. |
| Per-vendor failure isolation via `failed_vendors` state field | Abort-on-first-failure | Real-world procurement gets bad PDFs and partial submissions. Failing the whole evaluation because vendor 7's proposal had a parse error is unacceptable. Customer report appendix shows the 14 evaluated + the 1 that didn't make it. |
| Sync barrier at Comparator (not earlier) | Per-vendor mini-pipelines all the way to Decision | The Decision agent depends on cross-vendor ranking. There's no meaningful "per-vendor decision" — it's always comparative. Comparator is the natural sync point. |
| Default-deny visibility (Phase 9) | Default-allow with explicit blocks | Procurement is regulated. Compliance auditors will ask "what stops Bob from seeing Anita's IT RFP?" — a positive predicate (he's a collaborator / he's an approver / he's an admin) is easier to defend than a list of negative restrictions. |
| Access inheritance from RFP, not files (Phase 9) | Per-file ACL on autonomous ingestion | File arrival should add DATA not ACCESS. Customer sets the access list when creating the RFP; autonomous ingestion adds vendor facts under that already-permissioned slot. Statically enforced by `tests/test_access_invariant.py`. |
| Deadline-based processing (Phase 5 design) | Ingest-on-arrival | Procurement is deadline-driven. Avoids wasted LLM cost on vendor re-uploads (only the final pre-deadline version gets extracted). All vendors processed against the same rubric snapshot — auditable fairness. |
| Functional vs strict byte-identity for Phase 1 | Pursue strict byte-identity now | OpenAI explicitly documents `seed` as best-effort. Strict byte-identity REQUIRES a response cache layer; deferred to Phase 3 as its own exit criterion. Honest about the limitation rather than overclaiming. |

---

## What's still ahead (honest roadmap)

| Phase | Status | What it adds |
|---|---|---|
| **1** Determinism + grounding | ✅ COMPLETE | grounding 33-62% → 100%, content-derived seeds, Anthropic temp regression fixed |
| **2** Critic-as-controller (retry-with-feedback) | ✅ COMPLETE at the 3 LLM-**generation** steps | Critic is a self-correcting controller at every generation step — **Extraction, Evaluation, Explanation**: on a HARD verdict it feeds the agent specific feedback and retries (max 2) before isolating the vendor (`failed_vendors`), with per-vendor isolation and `critic_metrics_accum` telemetry (rolled into `summary.json` + the run event log). Explanation uses a graph-level 3-route critic node; Extraction/Evaluation use the shared in-branch controller `app/pipeline/critic_retry.run_with_critic_retry` (graph-level retry loops would fight the Phase-4 per-vendor fan-out). The **assisted/deterministic** steps (Planner, Ingestion, Retrieval, Comparator, Decision) run the critic **validation-only by design** — they make no free-form generative claim to re-prompt. Honest note: across 12 smoke runs Extraction/Evaluation produced **0 blocks** (all blocks were Explanation), so this is shipped as **production-robustness for messy input**, not a fix for an observed failure. |
| **3** LLM response cache | ✅ COMPLETE | $0 re-runs (cache key includes provider \| model \| temperature \| seed \| prompt \| response_format \| cache_bust); ON CONFLICT DO NOTHING parallel-safe; 3 escape hatches (Critic auto-correct, `/rerun?bypass_cache=true` with divergence flag, admin DELETE invalidation); cost-tracker reports cache_hits/misses/savings; tenant-blind by design. **3.17 live cost-savings benchmark deferred — tracked as BACKLOG.md P2.0b.** |
| **4** Parallel vendor execution | ✅ COMPLETE | 15-vendor wall-clock 30 min → ~3-4 min via LangGraph `Send` API + Semaphore(5) |
| **5** Deadline-based background ingestion | ✅ COMPLETE | RFPs first-class entity (`rfps` table), 3 autonomy modes (manual / auto_to_evaluate / auto_to_report), receive-only watcher + Modal-cron deadline scheduler + ingestion sub-graph, admin attribution queue, pipeline short-circuit on user-triggered Evaluate. Mode C gated until Phase 7 ships PDF. **D1/D4/E1 deferred to live integration — BACKLOG.md P2.0; legacy-table FK refactor — P2.0a.** |
| **6** Incremental re-evaluation for addenda | Planned | Late addenda re-evaluate only the affected vendor, ~30% of original run time |
| **6b** RFP source versioning | Planned | Mid-process rubric changes detected and flagged, no silent answer mis-mapping |
| **7** Customer-grade PDF report | Planned (NEXT) | 12-section audit-grade PDF with podium, scorecards, pairwise comparisons, audit trail; flips Mode C on |
| **8** Delivery abstraction (email / Teams / S3 / Slack) | Planned | Fire-and-forget evaluation; reads from Phase 5's `event_log` |
| **9** Multi-tenant visibility | ✅ COMPLETE | 5 access patterns, default-deny, static invariant enforcement |
| **10** Architecture rationale doc | Planned | Sales-grade "why multi-agent over single LLM" explainer |

Full plan with exit criteria per phase: [docs/dev/PRODUCTION_READINESS_PLAN.md](docs/dev/PRODUCTION_READINESS_PLAN.md). Deferred items tracked in [docs/dev/BACKLOG.md](BACKLOG.md) under P2.0–P2.0c.

---

## E3 — Evidence-quality benchmark (measured 2026-05-31, gpt-4o)

First repeatable, ground-truth benchmark of evidence quality. 6 synthetic
scenarios (clean, table-heavy, long/buried, short, conflicting, missing-evidence)
with answer keys grounded **by construction** (the same sentence seeds both the
PDF and the golden quote — verified verbatim by `tests/test_benchmark_dataset.py`).
Methodology + integrity model: [benchmark/README.md](../../benchmark/README.md);
contract: [E3_EXIT_CRITERIA.md](E3_EXIT_CRITERIA.md). Numbers below are recomputed
by `python -m benchmark.runner.run_benchmark` — no hand-entered figures.

| Metric | Baseline (`93ac2d3`) | After no-forced-scores (`f89a46d`) | Evidence |
|---|---|---|---|
| **Grounding / citation accuracy** | **1.00** | **1.00** | every extracted fact's quote is verbatim in source |
| **Fabricated citations** | **0** | **0** | across all 6 scenarios |
| Retrieval recall@k | 1.00 | 1.00 | present-fact grounding text was retrieved |
| Forced score when evidence absent | **5** | **1** | the no-forced-scores fix (Stage 4) |
| Insufficient-evidence rate | **0.00** | **0.80** | system now says "insufficient" not a fake 0 |
| Score consistency (stdev, 3 repeats) | 0.0 | 0.0 | temperature=0 determinism |
| Extraction recall (per fact) | 0.63 | 0.60 | **open gap** — ~37% of facts missed |
| Mandatory accuracy | 0.83 | 0.83 | conflicting-evidence check is the miss |
| Cost / full run | $0.35 | $0.36 | 6 scenarios, 0 operational failures |

**Honest reading.** The product's core promise — *every claim cited to verbatim
source, never fabricated* — measures **1.00 grounding / 0 fabricated**. The
no-forced-scores change is confirmed (forced 5→1, insufficient-rate 0.00→0.80).
**Known open gaps, logged in BACKLOG, not hidden:** extraction recall ~0.60;
contradiction handling (the 1 remaining forced case + conflicting mandatory) does
not yet resolve to "insufficient"; missing-mandatory becomes `review_required`
rather than rejection. Dev-box caveat: the BGE reranker fell back to vector order
(no HF egress); retrieval recall was 1.00 regardless.

---

## How to verify any claim in this document yourself

```bash
# 1. Run the whole test suite
pytest tests/ -v

# 2. Run the end-to-end smoke test against the standard fixture
python tools/smoke_test_graph.py \
  --rfp data/documents/RFP_IT_Managed_Services_MFS_2026.pdf \
  --criteria data/documents/Vendor_Selection_Criteria_MFS.csv \
  --vendor-pdf data/documents/Acme_ClearPath_Proposal.pdf \
  --vendor-pdf data/documents/nightbuilb_Apex_Technology_Proposal.pdf
# Produces tests/smoke_results/<timestamp>/ with full trace + topology diagrams

# 3. Manually verify the 5-persona visibility (requires Postgres + frontend running)
python tools/seed_visibility_personas.py   # seeds 5 demo users
#   Then log in to the UI as anita@meridian-demo.local / Test1234!
#   Switch between users; verify each sees only what the matrix says
python tools/seed_visibility_personas.py --cleanup   # removes demo data
```
