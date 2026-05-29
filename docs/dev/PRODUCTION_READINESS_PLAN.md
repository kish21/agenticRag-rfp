# Plan: True Agentic RAG — production-grade RFP evaluation platform

## Context

Today's 9-agent RFP-evaluation pipeline runs as a **fixed linear DAG** in LangGraph. The Critic agent runs *inline* inside each node (via `_hard_block_if`) and can only block — it cannot redirect or retry. Three back-to-back smoke runs against the same RFP + vendor set produced grounding_completeness of **62%, 36%, 33%** — same input, different output. Diagnostic instrumentation revealed the root cause: the Explanation LLM fabricates `source_chunk_id`s for system-computed claims (decision rank, scores, mandatory-check IDs) that don't exist in any PDF chunk.

This plan moves the system from "research demo" to "production-grade Agentic RAG" through ten phases. Each phase has explicit **exit criteria** that must ALL be satisfied before moving to the next phase. No phase is "done" because the code compiles — it is "done" because the listed evidence exists and the listed tests pass.

The plan answers seven concrete customer questions raised during review:
1. Why a chain of agents instead of one LLM? → Phase 10 architecture rationale.
2. RFP files arrive via folder/email — why aren't they pre-processed? → Phase 5.
3. 15 vendors should run in parallel. → Phase 4.
4. Vendors send addenda after initial submission — how is this handled? → Phase 6.
5. The customer needs a detailed audit-grade report. → Phase 7.
6. Some users want to fire-and-forget and receive the result by email. → Phase 8.
7. Multiple departments and concurrent RFPs — what does each user see at login? → Phase 9.

---

## Phase ordering and dependencies

```
Phase 1 (Foundations)                ← MUST be first; blocks everything else
   ├── Phase 2 (Critic-as-controller)
   │      └── Phase 4 (Parallel vendor execution)
   ├── Phase 3 (LLM response cache)      ← do last so cache key includes prompt evolutions
   ├── Phase 5 (Background ingestion)
   │      └── Phase 6 (Incremental re-evaluation)
   │            └── Phase 6b (RFP source versioning)
   ├── Phase 7 (Detailed PDF report)
   │      └── Phase 8 (Delivery abstraction)
   └── Phase 9 (Multi-user visibility)   ← independent track, parallelisable

Phase 10 (Architecture rationale doc)    ← alongside Phase 1, no code dependency
```

Recommended sequential execution (~17 working days):
1. Phase 1 + Phase 10 doc (1 day)
2. Phase 9 visibility (2 days) — unblocks enterprise demos
3. Phase 4 parallel (1 day) — biggest performance win
4. Phase 2 critic-as-controller (2 days)
5. Phase 7 PDF report (2 days)
6. Phase 5a → 5b → 5c background ingestion (3.5 days)
7. Phase 8 delivery (2 days)
8. Phase 6 + 6b incremental re-eval (3 days)
9. Phase 3 LLM cache (1 day)

Retry budget across the system: **max 2 retries per agent (3 total attempts)**.

---

## Verification methodology (applies to every phase)

Each phase carries a checklist of **exit criteria**. Before declaring a phase complete:

1. Every checkbox in the exit criteria must be ticked with concrete evidence (test name, commit SHA, screenshot, or DB query output) recorded in the PR description.
2. All existing tests must still pass — no regressions in `tests/regression/`, `tools/contract_tests.py`, `tools/checkpoint_runner.py status`.
3. The end-to-end smoke test (`tools/smoke_test_graph.py`) must reach `status='complete'` on the standard fixture (RFP_IT_Managed_Services + Acme + Apex). If the phase changes pipeline output shape, regenerate the smoke-test golden and document the diff in the PR.
4. The phase's own integration tests must run in CI and be visible on the PR.
5. Add a one-line entry to `.claude/daily_build_log.md` and update `CLAUDE.md`'s "Current build state".

If any exit criterion is in doubt, do NOT advance. The plan is sized so each phase's evidence is unambiguous.

---

## Phase 1 — Foundations: grounding bug fix + full determinism

### Intent
Eliminate the two root causes of non-determinism / non-reproducibility before building anything else on top. Without this, every later phase's retries, parallelism, and cache hits are unstable.

### Workstream 1a — Grounding bug fix (categorize claims)

**Problem:** [app/agents/explanation.py:58-91](app/agents/explanation.py#L58-L91) (`_build_fact_context` + `_build_compliance_summary` + `decision_context`) feeds the LLM both PDF facts AND system-computed metadata (rank, score, check_id), then the prompt at [app/prompts/explanation/generate_narrative.yaml](app/prompts/explanation/generate_narrative.yaml) tells the LLM that *every* claim must cite a `source_chunk_id`. For metadata claims this is impossible, so the LLM fabricates chunk_ids.

**Fix:**
- Edit [app/schemas/schema_decision.py:57-70](app/schemas/schema_decision.py#L57-L70). Extend `SynthesisLLMResponse`:
  ```python
  class SystemFact(BaseModel):
      fact_text: str
      origin: Literal["decision", "evaluation", "extraction", "comparator"]
      origin_id: str   # check_id | criterion_id | vendor rank | etc.

  class SynthesisLLMResponse(BaseModel):
      ...
      grounded_claims: List[GroundedClaim] = []    # PDF-cited
      system_facts: List[SystemFact] = []          # no grounding required
  ```
- Mirror on `VendorNarrative`: add `system_facts: List[SystemFact] = []`.
- Update `_generate_vendor_narrative` to populate `system_facts` directly from `synthesis.system_facts` without verification.
- Update `grounding_completeness` denominator to count only `grounded_claims + ungrounded_examples` (NOT `system_facts`).
- Rewrite [app/prompts/explanation/generate_narrative.yaml](app/prompts/explanation/generate_narrative.yaml) with two clearly separated sections: "PDF-EXTRACTED EVIDENCE — quote verbatim into `grounded_claims`" and "SYSTEM-COMPUTED METADATA — report into `system_facts`, do NOT quote, do NOT cite chunk_ids".

### Workstream 1b — Determinism

**Problem:** [app/providers/llm.py:135-157](app/providers/llm.py#L135-L157) — the Anthropic branch silently drops `temperature` (defaults internally to ~1.0). No provider has `seed` plumbed.

**Fix:**
- Extend `call_llm()` signature: `temperature: float = 0.0` (was 0.1), add `seed: Optional[int] = None`.
- Anthropic branch: pass `temperature=temperature` to `client.messages.create(...)`.
- OpenAI/Azure/OpenRouter/Modal branches: pass both `temperature` and `seed`.
- Add `stable_seed(*parts) → int` helper: `int(sha256("|".join(parts)).hexdigest()[:8], 16)`.
- Every agent passes `seed=stable_seed(run_id, agent_name, vendor_id)` when calling `call_llm()`.
- Audit every `call_llm(` callsite — if a non-zero temperature was set explicitly, change to 0.0 unless documented otherwise.

### Files
- [app/schemas/schema_decision.py](app/schemas/schema_decision.py), [app/agents/explanation.py](app/agents/explanation.py), [app/prompts/explanation/generate_narrative.yaml](app/prompts/explanation/generate_narrative.yaml), [app/providers/llm.py](app/providers/llm.py), every `call_llm()` callsite.

### Exit / pass criteria — Phase 1  ✅ COMPLETE 2026-05-28

- [x] `SystemFact` model exists in `schema_decision.py`; `SynthesisLLMResponse` and `VendorNarrative` both expose `system_facts: List[SystemFact]`.
- [x] `app/providers/llm.py` `call_llm()` signature includes `temperature: float = 0.0` and `seed: Optional[int] = None`; Anthropic branch passes `temperature=` to the SDK call (greppable proof).
- [x] `stable_seed()` helper exists in `app/providers/llm.py`; seed auto-derives from message hash when caller doesn't supply one (no agent-side code change required).
- [x] Every `call_llm(` callsite in `app/agents/*.py` either passes `temperature=0.0` explicitly OR relies on the new default; zero callsites pass `temperature>0` without an inline `# rationale:` comment.
- [x] **Functional determinism (REVISED — see note below):** smoke test runs twice consecutively produce identical shortlist, identical mandatory check outcomes, scores within ±0.05 raw points (verified `tests/smoke_results/20260528T125405Z` vs `20260528T130209Z`).
- [x] On both consecutive runs: `summary.json` shows `grounding_completeness == 1.0` (target was ≥ 0.95).
- [x] On both runs: `final status == 'complete'`, `decision_output` is non-null.
- [x] New test `tests/test_determinism.py` with 8 cases (stable_seed determinism, auto-seed derivation, explicit override, Anthropic temperature forwarding) — all passing.
- [x] **Phase 1c (added during execution):** all 5 `uuid.uuid4()[:8].upper()` callsites in `app/domain/criteria.py` replaced with `_stable_id(scope, kind, normalized_name)` — same RFP content now produces same criterion_ids across runs.
- [x] **Phase 1d (investigated during execution):** PDF text extraction proven byte-identical across processes; Qdrant-stored chunks byte-identical across runs; remaining LLM-output variance is OpenAI's documented "best-effort" seed limitation, not our code.

### Revised note on strict byte-identity

The original exit criterion called for byte-for-byte SHA256 identity of `decision_output.json` across two consecutive runs. Investigation proved this is **not achievable with raw LLM calls** — OpenAI explicitly documents `seed` as best-effort. The remaining variance is purely the LLM occasionally producing slightly different output for identical input (e.g., quoting `�` as-is vs expanding it to `"a3"`). All of our determinism plumbing (temperature=0, seed plumbed, content-hashed IDs, deterministic chunks) is correct.

**Strict byte-identity is moved to Phase 3 (LLM response cache) as an exit criterion there.** The cache returns the verbatim cached response, bypassing the LLM's best-effort sampling. Phase 1's exit criterion is amended to "functional determinism" (identical shortlist, scores within tolerance), which we have achieved.

---

## Phase 2 — Critic-as-controller, staged rollout

### Intent
Promote the Critic from inline function call to an explicit LangGraph node that can route a failing agent to RETRY (with feedback) instead of just BLOCK. This is what makes the system truly Agentic RAG: every step has a quality gate that can self-correct.

### Workstream 2a — Pattern around Explanation only

**Pattern:** insert a `critic_node` after Explanation. It reads the just-completed agent's output, runs the existing `critic_after_explanation()`, and routes to one of three outcomes:
- `APPROVED` → continue to END.
- `BLOCKED` + `retry_count < 2` → loop back to `explanation_node` with structured feedback.
- `BLOCKED` + `retry_count >= 2` → END with blocked sentinel.

**State changes** — extend [app/pipeline/state.py](app/pipeline/state.py) (additive):
```python
explanation_retry_count: int        # 0..2
explanation_critic_feedback: str    # what the previous critic said
```

**Graph topology** — edit [app/pipeline/graph.py](app/pipeline/graph.py):
```
... → decision → explanation → explanation_critic → routing
                       ↑                                │
                       └─ retry (feedback in state) ───┘
                                                  → continue → END
                                                  → END  (retries exhausted)
```

**Structured feedback** derived from `ungrounded_examples`:
> "Previous attempt had grounding_completeness=X. The following 3 representative claims were ungrounded: [...]. For SYSTEM-COMPUTED metadata use `system_facts` array — do NOT cite chunk_ids."

**Explanation node consumes feedback** — edit `run_explanation_agent` to accept optional `critic_feedback: str` and inject as a "PREVIOUS ATTEMPT FAILED — fix per this feedback:" section in the user prompt.

**Remove inline `_hard_block_if(exp_critic, ...)`** from `explanation_node` — that decision now belongs to `explanation_critic_node`. The explanation node returns `{"explanation_output": exp_out}` always.

**Recursion limit:** apply `evaluation_graph.with_config({"recursion_limit": 50})` so cycles can't hang the runtime.

### Workstream 2b — Extract reusable helper

After 2a is green, factor the pattern into `app/pipeline/critic_router.py`:
```python
def make_critic_node(
    agent_name: str,
    output_key: str,
    critic_fn: Callable[[Any, dict], CriticOutput],
    feedback_builder: Callable[[CriticOutput, Any], str],
    max_retries: int = 2,
) -> tuple[Callable, Callable]:    # returns (critic_node_fn, route_fn)
```
Re-implement `explanation_critic_node` via this helper. Existing tests must still pass.

### Workstream 2c — Roll out to other agents (each its own PR)

Priority order based on observed flakiness:
1. **Retrieval critic** — high value (low-confidence retrieval cascades). Feedback: "previous retrieval had confidence X; refine query, broaden terms."
2. **Extraction critic** — verify per-fact grounding. Feedback: "N facts had quotes not in source — re-extract just those facts."
3. **Evaluation critic** — rubric application consistency.
4. **Planner / Ingestion / Comparator / Decision** — defer; have been reliable in smoke runs.

### Files
- [app/pipeline/state.py](app/pipeline/state.py), [app/pipeline/graph.py](app/pipeline/graph.py), [app/pipeline/nodes.py](app/pipeline/nodes.py), [app/pipeline/critic_router.py](app/pipeline/) (new), [app/agents/explanation.py](app/agents/explanation.py), [tests/test_explanation_critic_loop.py](tests/) (new).

### Exit / pass criteria — Phase 2
- [ ] `app/pipeline/critic_router.py` exists with `make_critic_node()` and is unit-tested.
- [ ] `state.py` exposes `explanation_retry_count` and `explanation_critic_feedback`.
- [ ] `graph.py` topology includes `explanation_critic` node with three labeled edges: `continue→END`, `retry→explanation`, `exhausted→END`.
- [ ] `explanation_node` no longer raises on critic failure — it always returns `{"explanation_output": exp_out, ...}`.
- [ ] `tests/test_explanation_critic_loop.py` has 4 named test cases — `test_happy_path`, `test_retry_succeeds_on_attempt_2`, `test_exhausted_after_3_attempts`, `test_feedback_propagates_to_retry` — all passing.
- [ ] A deliberately-broken explanation prompt (forces critic block) blocks after exactly 3 attempts; `agent_events.json` shows three `explanation.*` events in sequence + one `explanation.blocked`.
- [ ] A previously-blocking smoke fixture (33% grounded) now reaches `status='complete'` because retry-with-feedback fixes the issue (verified by inspecting `summary.json` showing `explanation_retry_count >= 1`).
- [ ] LangGraph `recursion_limit=50` set; verified by a test that simulates a graph attempting >50 transitions and fails fast.
- [ ] Smoke test on standard fixture passes without retries needed (grounding_completeness ≥ 0.95 on attempt 1).

---

## Phase 3 — LLM response cache

### Intent
Make re-runs of the same input free, fast, and bit-exact. Required for: dev iteration speed, customer demo replays, audit/compliance bit-exact reproduction, customer bug reports they can "share a cache key" for.

### Schema
```sql
CREATE TABLE llm_response_cache (
    cache_key       TEXT PRIMARY KEY,   -- SHA256(provider|model|temperature|seed|system|user_messages|response_format)
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    response        TEXT NOT NULL,
    prompt_tokens   INT,
    completion_tokens INT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    hit_count       INT DEFAULT 0
);
CREATE INDEX idx_llm_cache_created ON llm_response_cache(created_at);
```

### Wiring
Wrap `call_llm()` in [app/providers/llm.py](app/providers/llm.py): build cache key → look up → on hit return cached + increment `hit_count`; on miss dispatch → store. Critic retry calls MUST pass `use_cache=False` — otherwise retries get the same broken response.

### Controls
- `LLM_CACHE_ENABLED=true|false` env var (default `true` in dev, `false` in production-real-LLM-cost test runs).
- `--no-cache` flag on `tools/smoke_test_graph.py`.
- Cache hits/misses surfaced via [app/infra/cost_tracker.py](app/infra/cost_tracker.py).

### Files
- [app/db/schema.sql](app/db/schema.sql), [app/providers/llm.py](app/providers/llm.py), [app/infra/cost_tracker.py](app/infra/cost_tracker.py), [tools/smoke_test_graph.py](tools/smoke_test_graph.py), [tests/test_llm_cache.py](tests/) (new).

### Exit / pass criteria — Phase 3
- [ ] `llm_response_cache` table exists in PostgreSQL; can verify with `\d llm_response_cache`.
- [ ] `call_llm()` accepts `use_cache: bool = True` parameter; greppable in source.
- [ ] First smoke run: average per-LLM-call latency ≥ 500ms (real provider calls).
- [ ] Second smoke run with `LLM_CACHE_ENABLED=true`: total wall-clock < 30 seconds (vs ~5 min uncached); cache hit rate ≥ 95% in cost tracker summary.
- [ ] `--no-cache` flag on smoke_test_graph.py forces all calls to be misses; verified by checking `hit_count` did NOT increment for any row created in that run.
- [ ] `tests/test_llm_cache.py` exists with at least 5 cases: `test_hit_returns_cached`, `test_miss_dispatches`, `test_whitespace_sensitivity` (different prompts = different keys), `test_retry_bypasses_cache` (Phase 2 retry must NOT hit cache), `test_seed_in_key` (different seeds = different keys).
- [ ] Cost tracker reports cache savings in `summary.json` of each smoke run.
- [ ] Documentation: README has a section "LLM caching" explaining controls and invalidation.
- [ ] **Byte-identity (deferred from Phase 1):** with `LLM_CACHE_ENABLED=true`, two consecutive smoke runs must produce SHA256-identical `decision_output.json` after normalising run-specific fields (`decision_id`, `run_id`, `setup_id`, `rfp_id`, timestamps). This is the strict reproducibility guarantee that raw LLM seed best-effort cannot deliver.

---

## Phase 4 — Parallel vendor execution (LangGraph `Send` API)

### Intent
For 15 vendors, today's sequential per-vendor loops would take 30+ minutes. Fan-out via LangGraph `Send` reduces wall-clock to roughly the time of the slowest single vendor.

### Approach
Refactor each vendor-iterating node (retrieval, extraction, evaluation, explanation) into a *fan-out + map* pattern. Each per-vendor task runs concurrently via `asyncio.gather` under LangGraph's hood. Bounded by `asyncio.Semaphore(MAX_VENDOR_CONCURRENCY)` (default 5) to respect OpenAI TPM and Qdrant pool limits.

Combined with Phase 2's critic-as-controller: each per-vendor sub-task has its own retry budget; one vendor failing does NOT abort the batch. Failed vendors are surfaced in a new state field `failed_vendors: list[dict]` and reported as an appendix in the final PDF.

### Files
- [app/pipeline/graph.py](app/pipeline/graph.py), [app/pipeline/nodes.py](app/pipeline/nodes.py), [app/pipeline/state.py](app/pipeline/state.py), [tools/smoke_test_graph.py](tools/smoke_test_graph.py), [tests/test_parallel_fanout.py](tests/) (new).

### Exit / pass criteria — Phase 4
- [ ] All 4 vendor-iterating nodes (retrieval, extraction, evaluation, explanation) use `Send` API; no `for vid in vendor_ids:` loops remain in pipeline nodes.
- [ ] `MAX_VENDOR_CONCURRENCY` env var honored; a test confirms semaphore enforces it.
- [ ] `failed_vendors: list[dict]` field added to `PipelineState`.
- [ ] `tests/test_parallel_fanout.py` exists with at least 3 cases: `test_5_mock_vendors_parallel_under_2s`, `test_concurrency_bounded_at_5`, `test_one_vendor_failure_doesnt_abort_batch`.
- [ ] Smoke test with 5 real vendors completes in less than 0.4× the wall-clock of the same fixture run sequentially. Document both numbers in PR.
- [ ] Per-vendor retry budgets are independent: forcing vendor A's explanation to retry twice does NOT consume vendor B's retry budget. Tested.
- [ ] `tests/regression/` checkpoints still pass.

---

## Phase 5 — Event-driven background ingestion

### Intent
Vendor proposals arrive over days/weeks via folder, email, or cloud storage. The pipeline should ingest + extract them in the background as they arrive, so when the user clicks "Evaluate" the data is already in PostgreSQL. End-to-end user-perceived latency drops from ~5 min to ~30 sec.

### Grounding correction — what actually exists today (added 2026-05-29)

The original Phase 5 design assumed an `rfps` table, an `invited_vendors` table, and a per-RFP creation flow already existed. **None of these exist in the current codebase.** Today an "RFP" is just a `rfp_id` string label generated on-the-fly inside the `/api/v1/evaluate/start` endpoint ([app/api/evaluation_routes.py:74](app/api/evaluation_routes.py#L74)) where the user uploads the RFP file plus all vendor files together in one HTTP multipart form. There is no concept of vendors uploading over time.

Phase 5 therefore has a **Phase 5.0 foundation** step that must precede 5a/5b/5c — creating the `rfps` and `invited_vendors` tables, building the RFP-creation API + UI, and provisioning the drop-folder convention. The existing single-upload form is preserved as the implementation of `autonomy_mode='manual'` so existing demos/customers continue to work unchanged.

Honest revised estimate: **~3 weeks** (not 3.5 days). Delivered as 5 PRs (PR-A through PR-E).

### 5.0 — Foundation prerequisites (NEW — must precede 5a)

**New tables:**
```sql
CREATE TABLE rfps (
  rfp_id              TEXT PRIMARY KEY,           -- existing rfp_id convention; not a UUID FK on legacy tables
  org_id              UUID NOT NULL,
  title               TEXT NOT NULL,
  department          TEXT,
  created_by_email    TEXT NOT NULL,
  created_at          TIMESTAMPTZ DEFAULT now(),
  submission_deadline TIMESTAMPTZ,                -- nullable; UI default = created_at + 14 days
  submission_status   TEXT NOT NULL DEFAULT 'open'
      CHECK (submission_status IN ('open','closed','processing','facts_ready','evaluated')),
  autonomy_mode       TEXT NOT NULL DEFAULT 'auto_to_evaluate'
      CHECK (autonomy_mode IN ('manual','auto_to_evaluate','auto_to_report'))
);

CREATE TABLE invited_vendors (
  rfp_id      TEXT NOT NULL REFERENCES rfps(rfp_id) ON DELETE CASCADE,
  vendor_id   TEXT NOT NULL,
  vendor_name TEXT,
  invited_by  TEXT NOT NULL,
  invited_at  TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (rfp_id, vendor_id)
);

CREATE TABLE event_log (
  event_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type  TEXT NOT NULL,    -- 'rfp.facts_ready' | 'rfp.evaluation_complete' | 'rfp.late_addendum' | 'rfp.attribution_failed'
  org_id      UUID NOT NULL,
  rfp_id      TEXT NOT NULL,
  payload     JSONB NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ DEFAULT now(),
  delivered_at TIMESTAMPTZ                       -- set by Phase 8 dispatcher, null = not yet delivered
);
CREATE INDEX ix_event_log_pending ON event_log(created_at) WHERE delivered_at IS NULL;
```

**Existing tables — NOT refactored in Phase 5.** `evaluation_runs`, `vendor_documents`, `extracted_facts` keep their plain `rfp_id TEXT` columns. The relationship between `rfps.rfp_id` and the legacy tables is application-enforced, not FK-enforced. (Tracked as a follow-up cleanup post-Phase-5.)

**Mode semantics:**
- `manual` — today's behaviour. Customer uses the existing single-form upload at `/api/v1/evaluate/start`. No watcher activity. Files in `drops/` are ignored.
- `auto_to_evaluate` (default) — Phase 5 watcher receives files; deadline scheduler processes through extraction; stops at `facts_ready`. Emits `rfp.facts_ready` event. Customer clicks Evaluate → ~30s.
- `auto_to_report` — schema-accepted from day 1, but the scheduler rejects with "Phase 7 PDF not yet implemented" until Phase 7 ships. Falls back to `auto_to_evaluate` behaviour.

**RFP creation flow (new API + UI):**
- `POST /api/v1/rfps` — create RFP shell (title, department, deadline, autonomy_mode). Returns `rfp_id`.
- `POST /api/v1/rfps/{rfp_id}/vendors` — invite vendor (creates `invited_vendors` row + provisions `drops/{rfp_id}/{vendor_id}/` folder).
- `POST /api/v1/rfps/{rfp_id}/deadline` — set/extend deadline (only while `submission_status='open'`).
- `GET /api/v1/rfps/{rfp_id}` — RFP summary with vendor list, status, deadline, received-files count per vendor.
- Frontend page `frontend/app/procurement/rfps/new/page.tsx` — replaces the empty placeholder at `frontend/app/procurement/upload/page.tsx` which is preserved as the "manual mode" upload path.

### 5a — Attribution layer (defense in depth)

**Default mechanism: structured drop folders (path = attribution).**
```
drops/
  rfp-2026-it-managed-services/
    acme/                       ← pre-created at vendor-invite time
      proposal_v1.pdf
      addendum_2026-05-18.pdf
    apex/...
```
Folder = attribution. No LLM call needed for the common case.

**Optional: email-forwarder bot.** Provision per-RFP inbox; sender domain → vendor lookup. Add only if a customer requests email workflow.

**Fallback: LLM-based content attribution.** For root-dropped files or ambiguous senders: extract first 2 pages, ask LLM "(rfp_id, vendor_id, confidence)". Confidence ≥0.85 auto-attributes (audit-logged); below 0.85 → admin "needs attribution" queue with LLM reasoning.

**Critical safety check:** before ingesting, verify `invited_vendors` membership — uninvited vendors go to admin queue, never silently ingested.

### DESIGN PIVOT — deadline-based processing (revised 2026-05-28)

The original Phase 5 design ingested files immediately on arrival. Workflow review with the customer scenario in mind revealed a better model: **store on arrival, process after the submission deadline closes.** This matches how real procurement works (deadline-driven), avoids wasted compute on re-uploaded drafts, and guarantees all vendors are processed against the same rubric snapshot.

**Lifecycle:**
```
T0          Customer creates RFP. Sets submission_deadline (e.g. Friday 5pm).
            Invites vendors. Folders provisioned.   rfps.submission_status = 'open'

T1..Tn      Vendors upload (and re-upload) files throughout the window.
            Watcher RECEIVES each file — SHA256, attribution, INSERT into
            ingestion_jobs with status='received'. NO LLM calls, NO extraction.
            Re-uploads from the same vendor mark older versions superseded.

Deadline    rfps.submission_status flips: open → closed. Watcher rejects new
            uploads with 'submissions closed' error.

Deadline    Modal-scheduled deadline_processor cron (runs every 5 min) sees:
+ 1 hour    "rfps where submission_deadline < NOW() AND status='closed'".
grace       For each, fan out the received jobs through ingestion + extraction
            sub-graph IN PARALLEL across all vendors.
            rfps.submission_status: closed → processing.

Completion  When all ingestion_jobs reach status='facts_ready':
            rfps.submission_status: processing → facts_ready.
            Customer notified via Phase 8 channels (email + Teams + in-app).

Customer    Logs in, clicks 'Evaluate'. Pipeline short-circuits the heavy
returns     stages (facts already in PostgreSQL). Only Retrieval refresh,
            Evaluation, Comparator, Decision, Explanation actually run.
            ~30 seconds. Report ready.
```

**Why this is better than "ingest on arrival":**
- **No wasted extraction** on draft versions vendors will replace before deadline.
- **All vendors batch-processed together** against the same evaluation_setup snapshot — procurement fairness.
- **No half-state UI** ("Acme ready / Apex still processing") during submission window.
- **Zero LLM cost during submission window** — only storage.
- **Simpler watcher** — receives + stores, no sub-graph trigger.
- **Customer experience is sharper** — they get one "ready to evaluate" notification, not a stream of per-vendor processing updates.

### 5b — State / idempotency (`ingestion_jobs`)

`rfps.submission_deadline`, `rfps.submission_status`, and `rfps.autonomy_mode` are created in **Phase 5.0** above. This sub-section adds the per-file job table:

```sql
CREATE TABLE ingestion_jobs (
  job_id          UUID PRIMARY KEY,
  org_id          UUID NOT NULL,
  rfp_id          TEXT NOT NULL,
  vendor_id       TEXT NOT NULL,
  source_uri      TEXT,
  filename        TEXT,
  content_hash    CHAR(64) NOT NULL,
  status          TEXT NOT NULL,
  -- received       : file stored, awaiting deadline
  -- superseded     : older version of same vendor's submission
  -- queued         : deadline passed, ready for ingestion sub-graph
  -- processing     : ingestion + extraction in flight
  -- facts_ready    : extracted_facts rows written, ready for evaluation
  -- failed         : non-recoverable error during processing
  -- duplicate      : same content_hash already received
  -- needs_attribution : file landed with unresolvable vendor (admin queue)
  -- rejected_late  : file arrived after submission_deadline (hard deadline)
  attribution_confidence FLOAT,
  received_at     TIMESTAMPTZ DEFAULT now(),
  attempted_at    TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  error           TEXT,
  doc_id          UUID REFERENCES vendor_documents,
  superseded_by   UUID REFERENCES ingestion_jobs(job_id),
  UNIQUE (rfp_id, vendor_id, content_hash)
);
```

**On file arrival (watcher path):**
1. Compute SHA256.
2. `SELECT submission_status FROM rfps WHERE rfp_id = X` — if not `open`, write `status='rejected_late'`, return error to vendor.
3. INSERT job with `status='received'`. ON CONFLICT (same hash) → `status='duplicate'`, skip.
4. If a PRIOR job exists for `(rfp_id, vendor_id)` with `status='received'`, mark it `superseded`. New job becomes the active one.

**On deadline (scheduler path):**
1. Lock submissions: `UPDATE rfps SET submission_status='closed' WHERE submission_deadline < NOW() AND submission_status='open'`.
2. For each closed RFP, queue its received jobs: `UPDATE ingestion_jobs SET status='queued' WHERE rfp_id=X AND status='received'`.
3. Set RFP status to `processing`.
4. Fire the ingestion sub-graph for each queued job — IN PARALLEL across vendors.
5. When all jobs reach `facts_ready`, flip RFP status to `facts_ready`. Notify customer (Phase 8).

### 5c — Watcher service (receive-only) + deadline scheduler

**Watcher** — `app/jobs/ingestion_watcher.py`:
- `watchdog`-based local fs watcher + Modal-scheduled S3/Azure pollers.
- Receive-only: SHA256 + attribution + INSERT into `ingestion_jobs(status='received')`.
- Does NOT trigger any LLM/Qdrant work.
- ~50 lines.

**Deadline scheduler** — `app/jobs/deadline_processor.py` (NEW):
- Modal cron, runs every 5 minutes (same pattern as existing `app/jobs/cleanup.py`, `app/jobs/rate_monitor.py`).
- Atomically transitions RFPs across the lifecycle.
- Fires ingestion + extraction sub-graph in parallel for all queued jobs of an RFP.
- Emits the `rfp.facts_ready` event consumed by Phase 8 delivery channels.

**Ingestion sub-graph** — `app/pipeline/ingestion_graph.py`:
- Minimal: planner-lite → ingestion → extraction.
- One graph instance per `(rfp_id, vendor_id)` pair, fanned out in parallel by the deadline_processor.
- Writes facts to PostgreSQL with `setup_id` snapshot tag (so post-deadline rubric edits don't silently re-map old extractions — see Phase 6b).

**Pipeline short-circuit on user-triggered evaluation** — [app/pipeline/nodes.py](app/pipeline/nodes.py):
- `ingestion_node`: if `facts_already_extracted(vid, rfp_id)`, skip body.
- `extraction_node`: same.
- This is the mechanism that makes the user-triggered "Evaluate" click take ~30s instead of ~5min.

### Late submissions & addenda (post-deadline)

**Hard deadline.** Files arriving after `submission_deadline` are rejected at the watcher with `status='rejected_late'`. Vendor sees an error; customer sees them in an admin queue.

**Customer can explicitly accept a late addendum.** If they do:
- The late job is promoted from `rejected_late` to `queued`.
- Phase 6 (incremental re-evaluation) re-runs Extraction + Evaluation for that vendor only.
- Comparator + Decision + Explanation re-run with the updated vendor's score.
- Report explicitly highlights "Vendor X submitted addendum on YYYY-MM-DD, accepted by [user]" in the audit trail.

### Delivery plan — 5 PRs (revised 2026-05-29)

| PR | Scope | Files |
|---|---|---|
| **PR-A — Foundation schema** | `rfps`, `invited_vendors`, `ingestion_jobs`, `event_log` tables. Alembic migration `0006_phase5_foundation.py`. `app/db/fact_store.py` helpers. `app/domain/rfp.py` extended with `RFP` Pydantic model. | schema.sql, alembic/versions/0006_*, fact_store.py, domain/rfp.py, tests/test_phase5_schema.py |
| **PR-B — RFP creation API + UI** | `POST/GET /api/v1/rfps`, `POST /api/v1/rfps/{id}/vendors`, `POST /api/v1/rfps/{id}/deadline`. Frontend page `frontend/app/procurement/rfps/new/page.tsx`. Drop folder provisioning helper. | api/rfp_routes.py (NEW), frontend pages, tests/test_rfp_api.py |
| **PR-C — Watcher service** | `app/jobs/ingestion_watcher.py` (watchdog-based local fs). Path-based attribution. LLM-fallback attribution for root drops. Deadline-gate enforcement. | jobs/ingestion_watcher.py, jobs/llm_attribution.py, tests/test_ingestion_attribution.py, tests/test_ingestion_idempotency.py |
| **PR-D — Deadline processor + sub-graph** | `app/jobs/deadline_processor.py` (Modal cron). `app/pipeline/ingestion_graph.py` (3-node sub-graph). Modal schedule entries. Event emission on `facts_ready`. | jobs/deadline_processor.py, pipeline/ingestion_graph.py, deploy/modal.py, tests/test_deadline_lifecycle.py |
| **PR-E — Short-circuit + admin endpoints** | Pipeline short-circuit (skip ingestion/extraction nodes when facts present). Admin attribution queue API + UI. Late-addendum acceptance. | pipeline/nodes.py, api/admin_routes.py, frontend admin queue page, tests/test_pipeline_shortcircuit.py |

### Files (consolidated)
- [app/db/schema.sql](app/db/schema.sql) — `rfps`, `invited_vendors`, `ingestion_jobs`, `event_log` tables.
- [alembic/versions/0006_phase5_foundation.py](alembic/versions/) (NEW) — migration.
- [app/db/fact_store.py](app/db/fact_store.py) — `create_rfp()`, `invite_vendor()`, `set_deadline()`, `enqueue_ingestion_job()`, `mark_rfp_facts_ready()`, `get_rfp_rollup()`, `emit_event()`, `facts_already_extracted()`.
- [app/domain/rfp.py](app/domain/rfp.py) — `RFP`, `InvitedVendor`, `IngestionJob` Pydantic models + state-machine helpers.
- [app/api/rfp_routes.py](app/api/) (NEW) — RFP CRUD + vendor invite + deadline endpoints.
- [app/api/admin_routes.py](app/api/admin_routes.py) — attribution queue, late-addendum acceptance.
- [app/jobs/ingestion_watcher.py](app/jobs/) (NEW) — receive-only watcher.
- [app/jobs/deadline_processor.py](app/jobs/) (NEW) — Modal cron.
- [app/jobs/llm_attribution.py](app/jobs/) (NEW) — LLM fallback attribution.
- [app/jobs/email_watcher.py](app/jobs/) (DEFERRED — only built if a customer asks for email upload).
- [app/pipeline/ingestion_graph.py](app/pipeline/) (NEW) — sub-graph.
- [app/pipeline/nodes.py](app/pipeline/nodes.py) — short-circuit on `facts_already_extracted()`.
- [deploy/modal.py](deploy/modal.py) — schedules for watcher poller + deadline_processor.
- [frontend/app/procurement/rfps/new/page.tsx](frontend/app/procurement/rfps/) (NEW) — new RFP creation page.
- [frontend/app/procurement/admin/attribution-queue/page.tsx](frontend/app/procurement/admin/) (NEW) — admin queue.
- Tests: `test_phase5_schema.py`, `test_rfp_api.py`, `test_ingestion_attribution.py`, `test_ingestion_idempotency.py`, `test_deadline_lifecycle.py`, `test_pipeline_shortcircuit.py`.

### Exit / pass criteria — Phase 5 (revised, organised by PR)

Every criterion below is testable and has a documented evidence column. PR cannot merge without its criteria row marked `PASS` + evidence link.

#### PR-A — Foundation schema

| # | Criterion | Evidence required |
|---|---|---|
| A1 | `rfps`, `invited_vendors`, `ingestion_jobs`, `event_log` tables exist with the exact columns + CHECK constraints in 5.0. | `psql \d rfps`, `\d invited_vendors`, `\d ingestion_jobs`, `\d event_log` output pasted in PR description. |
| A2 | Alembic migration `0006_phase5_foundation.py` applies cleanly to a fresh DB AND downgrades cleanly. | CI step: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`. |
| A3 | CHECK constraint on `submission_status` rejects invalid values. | `tests/test_phase5_schema.py::test_invalid_submission_status_rejected` green. |
| A4 | CHECK constraint on `autonomy_mode` rejects invalid values. | `tests/test_phase5_schema.py::test_invalid_autonomy_mode_rejected` green. |
| A5 | UNIQUE constraint on `ingestion_jobs(rfp_id, vendor_id, content_hash)` rejects duplicates. | `tests/test_phase5_schema.py::test_duplicate_content_hash_rejected` green. |
| A6 | `fact_store.create_rfp()`, `invite_vendor()`, `set_deadline()`, `enqueue_ingestion_job()`, `mark_rfp_facts_ready()`, `emit_event()`, `facts_already_extracted()` exist and are unit-tested. | 7 named test functions in `test_phase5_schema.py`, all green. |
| A7 | `RFP` Pydantic model in `app/domain/rfp.py` enforces autonomy_mode + submission_status enums. | `tests/test_phase5_schema.py::test_rfp_model_validation` green. |

#### PR-B — RFP creation API + UI

| # | Criterion | Evidence required |
|---|---|---|
| B1 | `POST /api/v1/rfps` creates an RFP shell with default `autonomy_mode='auto_to_evaluate'` and default `submission_deadline = now() + 14 days` when omitted. | `tests/test_rfp_api.py::test_create_rfp_defaults` green. |
| B2 | `POST /api/v1/rfps/{id}/vendors` creates `invited_vendors` row AND provisions `drops/{rfp_id}/{vendor_id}/` folder on disk. | `tests/test_rfp_api.py::test_invite_vendor_provisions_folder` green. |
| B3 | `POST /api/v1/rfps/{id}/deadline` rejects extension after `submission_status` ≠ `open` with HTTP 409. | `tests/test_rfp_api.py::test_deadline_locked_after_close` green. |
| B4 | RBAC: only users in the RFP's department or with `platform_admin` role can create/edit. | `tests/test_rfp_api.py::test_rbac_rfp_create` green (2 cases). |
| B5 | Phase 9 invariant respected: RFP creation does NOT write to `user_departments` / `rfp_collaborators` / `approval_assignments`. | `tests/test_access_invariant.py` still green. |
| B6 | Frontend page at `/procurement/rfps/new` renders, accepts the 4 required fields, calls the API, and redirects to the new RFP detail page. | Manual screenshot in PR description + frontend e2e test. |
| B7 | Existing `/api/v1/evaluate/start` (manual upload) still works unchanged for `autonomy_mode='manual'`. | `tools/smoke_test_graph.py` still passes on the standard fixture. |

#### PR-C — Watcher service

| # | Criterion | Evidence required |
|---|---|---|
| C1 | `python -m app.jobs.ingestion_watcher` starts cleanly, watches all `drops/*/*/` folders. | Process launches, log line confirms watch set. |
| C2 | Drop `proposal.pdf` into `drops/{rfp_id}/{vendor_id}/` BEFORE deadline → `ingestion_jobs` row appears with `status='received'` within 5 seconds; NO `extracted_facts` rows; NO Qdrant chunks. | `tests/test_ingestion_attribution.py::test_path_based_attribution` green. |
| C3 | Drop file AFTER deadline → `status='rejected_late'`. | `tests/test_ingestion_attribution.py::test_late_rejection` green. |
| C4 | Drop file for vendor NOT in `invited_vendors` → `status='needs_attribution'`. | `tests/test_ingestion_attribution.py::test_uninvited_vendor` green. |
| C5 | Same vendor drops 2 different files before deadline → 1st marked `superseded`, 2nd becomes `received`. | `tests/test_ingestion_idempotency.py::test_supersede_on_reupload` green. |
| C6 | Same content hash dropped twice → 2nd marked `duplicate`. | `tests/test_ingestion_idempotency.py::test_duplicate_hash` green. |
| C7 | Drop into root `drops/{rfp_id}/` (no vendor folder) → LLM attribution runs; confidence ≥0.85 auto-attributes (audit-logged), <0.85 → `needs_attribution`. | `tests/test_ingestion_attribution.py::test_llm_fallback_high_confidence` + `test_llm_fallback_low_confidence` green. |
| C8 | Watcher survives PostgreSQL reconnect (kill+restart postgres container; watcher resumes). | Integration test `tests/test_ingestion_idempotency.py::test_watcher_pg_reconnect` green. |

#### PR-D — Deadline processor + sub-graph

| # | Criterion | Evidence required |
|---|---|---|
| D1 | `python -m app.jobs.deadline_processor` runs as Modal cron; visible in `modal app list`. | Modal dashboard screenshot. |
| D2 | Set `rfps.submission_deadline = NOW() - 1 minute` → within one cron tick (≤5 min), `submission_status` flips `open → closed → processing`. | `tests/test_deadline_lifecycle.py::test_deadline_triggers_close` green. |
| D3 | All `ingestion_jobs(status='received')` for that RFP flip to `queued`, then `processing`, then `facts_ready`. | `tests/test_deadline_lifecycle.py::test_jobs_advance_through_states` green. |
| D4 | Vendors fan out IN PARALLEL — 5-vendor fixture finishes in <0.4× sequential wall-clock. | Benchmark log in PR description. |
| D5 | When all jobs reach `facts_ready`, `rfps.submission_status` flips to `facts_ready` AND `event_log` row with `event_type='rfp.facts_ready'` is created. | `tests/test_deadline_lifecycle.py::test_facts_ready_emits_event` green. |
| D6 | `autonomy_mode='auto_to_report'` is accepted by schema but scheduler rejects with `event_type='rfp.evaluation_failed'` reason "Phase 7 PDF not yet implemented". | `tests/test_deadline_lifecycle.py::test_mode_c_gated` green. |
| D7 | `autonomy_mode='manual'` RFPs are SKIPPED by the scheduler entirely — no state transitions, no LLM calls. | `tests/test_deadline_lifecycle.py::test_manual_mode_untouched` green. |
| D8 | Ingestion sub-graph writes `extracted_facts` with `setup_id` snapshot tag (rubric frozen at deadline). | `tests/test_deadline_lifecycle.py::test_setup_id_snapshot` green. |

#### PR-E — Short-circuit + admin endpoints

| # | Criterion | Evidence required |
|---|---|---|
| E1 | User-triggered `/api/v1/evaluate/start` AFTER background processing completes in ≤60 seconds on 5-vendor fixture. | Benchmark log + `agent_events.json` showing ingestion/extraction events skipped. |
| E2 | Pipeline log records 5 `ingestion.skipped` events + 5 `extraction.skipped` events. | Greppable in `evaluation_runs.agent_events`. |
| E3 | `GET /api/v1/admin/attribution-queue` returns all `needs_attribution` jobs scoped to admin's org. | `tests/test_pipeline_shortcircuit.py::test_admin_queue_scoped` green. |
| E4 | `POST /api/v1/admin/attribution-queue/{job_id}/assign` lets admin assign to a vendor — job flips `needs_attribution → received` (or → `queued` if past deadline + accepted as late). | `tests/test_pipeline_shortcircuit.py::test_admin_assign` green. |
| E5 | `POST /api/v1/admin/late-addendum/{job_id}/accept` promotes `rejected_late → queued`. | `tests/test_pipeline_shortcircuit.py::test_late_addendum_accept` green. |
| E6 | All 65 existing checkpoints still pass: `python tools/checkpoint_runner.py status` shows 65/66 (Q09 above-threshold, unchanged). | CI checkpoint job green. |
| E7 | `tools/smoke_test_graph.py` on standard 2-vendor fixture still reaches `status='complete'` end-to-end. | Smoke run artifact attached to PR. |

### Test results tracking

A test-results table will be maintained at the top of each PR description in this format:

```
| Criterion | Status | Evidence |
|-----------|--------|----------|
| A1        | PASS   | logs/A1_psql_describe.txt |
| A2        | PASS   | CI run #1234 step 'alembic-roundtrip' |
| A3        | PASS   | tests/test_phase5_schema.py::test_invalid_submission_status_rejected |
| ...       | ...    | ... |
```

PR cannot be marked ready-for-review until every row is PASS. CI must run the named test functions explicitly (no broad `pytest` — names must match the criteria table).

### Phase 5 final acceptance test (must pass before Phase 5 declared complete)

A single scripted end-to-end scenario in `tests/test_phase5_e2e.py`:

1. Create RFP `e2e-phase5-test` with deadline NOW + 60 seconds, mode `auto_to_evaluate`.
2. Invite 3 vendors.
3. Drop 1 valid file per vendor into respective `drops/` folders.
4. Drop 1 duplicate of vendor 1's file (expect `duplicate`).
5. Drop 1 file for an UNINVITED vendor (expect `needs_attribution`).
6. Wait 60 seconds for deadline.
7. Wait ≤ 5 minutes for scheduler tick.
8. Assert: `submission_status='facts_ready'`, 3 ingestion_jobs in `facts_ready`, 1 in `duplicate`, 1 in `needs_attribution`.
9. Assert: `event_log` has exactly 1 row with `event_type='rfp.facts_ready'`.
10. Trigger user-evaluation via API; assert wall-clock ≤ 60 seconds.
11. Assert: final `evaluation_runs.status='complete'` with `decision_output` non-null.

This e2e test is the single source of truth for "Phase 5 is done."

---

## Phase 6 — Incremental re-evaluation (vendor addenda)

### Intent
Vendors send addenda, clarifications, late submissions. The system must re-evaluate ONLY the affected vendor without re-running the other 14 from scratch.

### Approach
Document versioning + LangGraph checkpointers + targeted re-runs.

**Schema:**
```sql
ALTER TABLE vendor_documents ADD COLUMN
    version INT DEFAULT 1,
    addendum_to UUID REFERENCES vendor_documents(doc_id),
    superseded_by UUID REFERENCES vendor_documents(doc_id) NULL;

ALTER TABLE extracted_facts ADD COLUMN
    doc_version INT DEFAULT 1,
    superseded_by UUID REFERENCES extracted_facts(fact_id) NULL;

ALTER TABLE evaluation_runs ADD COLUMN
    is_incremental BOOLEAN DEFAULT FALSE,
    incremental_vendors TEXT[] DEFAULT '{}';
```

**Checkpointer** — switch in-memory state to **`AsyncPostgresSaver`** in [app/pipeline/graph.py](app/pipeline/graph.py):
```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
checkpointer = AsyncPostgresSaver(connection_pool)
evaluation_graph = build_graph().with_config({"checkpointer": checkpointer})
```

**Re-run flow:**
1. Addendum arrives → ingestion_graph writes new chunks + new facts (version=2), marks old facts `superseded_by`.
2. New `evaluation_runs` row: `is_incremental=true, incremental_vendors=['acme']`.
3. New graph run pointed at the prior run's checkpoint; runs only Evaluation→Decision for `acme`.
4. Comparator + Decision re-run; other vendors reused from prior state.
5. Explanation includes "Changes since previous evaluation" section.

### 6b — RFP source versioning (extends 6)

The RFP itself can change. Without source versioning, vendor answers are silently mis-mapped to changed questions.

**Schema:**
```sql
ALTER TABLE rfps ADD COLUMN current_version INT DEFAULT 1;
ALTER TABLE evaluation_setups ADD COLUMN rfp_version INT DEFAULT 1;
ALTER TABLE evaluation_setups ADD UNIQUE (rfp_id, rfp_version, setup_id);
ALTER TABLE vendor_documents ADD COLUMN responded_to_rfp_version INT DEFAULT 1;
ALTER TABLE extracted_facts ADD COLUMN
    extracted_against_setup_id UUID,
    extracted_against_rfp_version INT;
```

When customer revises RFP source: bump `rfps.current_version`, write new `evaluation_setups`, diff old vs new criteria. UI clearly flags vendors as responding to v1 when current is v2, and shows "missing answer for newly-added criterion X".

### Files
- [app/db/schema.sql](app/db/schema.sql), [app/db/fact_store.py](app/db/fact_store.py), [app/pipeline/graph.py](app/pipeline/graph.py), [app/api/evaluation_routes.py](app/api/evaluation_routes.py), [app/pipeline/incremental_runner.py](app/pipeline/) (new), [app/domain/rfp.py](app/domain/rfp.py), [tests/test_incremental_reeval.py](tests/) (new), [tests/test_rfp_versioning.py](tests/) (new).

### Exit / pass criteria — Phase 6
- [ ] `AsyncPostgresSaver` is wired in `graph.py`; state durably persists per node — verified by querying LangGraph checkpoint table after a smoke run.
- [ ] Schema has `version`, `addendum_to`, `superseded_by` columns; greppable in schema.sql.
- [ ] Submit addendum for vendor A: new `vendor_documents` row with `version=2, addendum_to=<v1_doc_id>` exists; old `extracted_facts` rows have `superseded_by` set.
- [ ] Trigger incremental re-evaluation: `agent_events.json` shows extraction/evaluation invoked ONLY for vendor A; other vendors' nodes are skipped (event filter assertion).
- [ ] Comparator + Decision re-run with the updated A scores; PDF report (Phase 7) includes "Changes since previous evaluation" section.
- [ ] Incremental wall-clock < 30% of original full-run wall-clock on the standard fixture.
- [ ] RFP source revision: bump `rfps.current_version` to 2; verify `evaluation_setups` writes new version row, `app/domain/rfp.py diff_setups()` returns the correct added/removed/modified criteria list.
- [ ] Vendor responses are tagged with `responded_to_rfp_version=1` even after the RFP becomes v2.
- [ ] After RFP revision adding a NEW mandatory check, evaluation flags the vendor as "missing answer for MC-NEW" — not silently failed and not silently passed.
- [ ] `tests/test_incremental_reeval.py` and `tests/test_rfp_versioning.py` both passing.

---

## Phase 7 — Detailed customer-grade PDF report

### Intent
Procurement teams need a formal report that a CFO/legal can read, sign, and file. Current ExplanationOutput is minimal narrative; needed is a 10–12 section audit-grade document.

### Schema extensions
```python
class PodiumEntry(BaseModel):
    rank: int
    vendor_id: str
    vendor_name: str
    total_score: float
    score_delta_vs_next: float
    tipping_factor: str

class CriterionScorecard(BaseModel):
    criterion_id: str
    criterion_name: str
    weight: float
    per_vendor_scores: dict[str, float]
    rubric_used: str

class PairwiseComparison(BaseModel):
    winner_id: str
    runner_up_id: str
    narrative: str
    key_evidence: list[GroundedClaim]

class AuditTrailEntry(BaseModel):
    timestamp: datetime
    agent: str
    action: str
    detail: dict

class ExplanationOutput(BaseModel):           # extended
    ...
    winner_declaration: str
    decision_confidence: float
    podium: list[PodiumEntry]
    criterion_scorecards: list[CriterionScorecard]
    pairwise_comparisons: list[PairwiseComparison]
    mandatory_check_table: list[dict]
    rejection_reasons: dict[str, list[GroundedClaim]]
    audit_trail: list[AuditTrailEntry]
    risks_and_open_questions: list[str]
```

### Template — 12 sections
1. Cover page (RFP title, decision date, decision_id, decision confidence)
2. Executive summary
3. Winner declaration
4. Ranked podium with deltas
5. Per-criterion scorecard matrix (criterion × vendor)
6. Pairwise winner-vs-runner-up comparisons
7. Mandatory check pass/fail table with citations
8. Rejection rationale per rejected vendor
9. Approval routing
10. Methodology note (weights, retrieval stats, model versions, run cost)
11. Risks & open questions
12. Audit trail appendix

### Files
- [app/schemas/schema_decision.py](app/schemas/schema_decision.py), [app/agents/explanation.py](app/agents/explanation.py), [app/prompts/explanation/pairwise_comparison.yaml](app/prompts/explanation/) (new), [app/output/report_template.html](app/output/) (new), [app/output/pdf_report.py](app/output/pdf_report.py), [app/api/evaluation_routes.py](app/api/evaluation_routes.py), [tests/test_pdf_report.py](tests/) (new).

### Exit / pass criteria — Phase 7
- [ ] `ExplanationOutput` schema includes all 8 new fields listed above; Pydantic validates correctly.
- [ ] `app/output/report_template.html` exists with all 12 sections rendered in the right order from sample fixture data.
- [ ] `app/output/pdf_report.py render_pdf()` returns valid PDF bytes (test: first 4 bytes are `%PDF`).
- [ ] New endpoint `GET /api/v1/runs/{run_id}/report.pdf` returns HTTP 200 with `Content-Type: application/pdf`.
- [ ] Manual review: a non-engineer can read the report end-to-end and answer (a) who won, (b) why, (c) what each rejected vendor's specific failure was, (d) which approver needs to sign off, without needing further explanation.
- [ ] Audit trail section lists every agent event with timestamps; verified against `agent_events` table.
- [ ] `tests/test_pdf_report.py` includes a snapshot test against a golden HTML fixture (timestamps masked) — passes.
- [ ] Pairwise comparison narratives are grounded: every claim has a `grounding_quote` from one of the two vendors' chunks; verified by extending Phase 1's grounding-completeness check to pairwise narratives.
- [ ] Report renders correctly when one or more vendors failed (Phase 4 `failed_vendors` appendix appears with explanation).

---

## Phase 8 — Delivery abstraction

### Intent
Executives and approvers don't want to watch the pipeline. They want fire-and-forget — kick off evaluation, walk away, receive the finished PDF in their inbox / shared folder / Teams channel.

### Approach
Pluggable channel modules + subscription model + retry with exponential backoff.

```
app/delivery/
├── base.py              # DeliveryChannel ABC
├── email_smtp.py        # SMTP / SendGrid / SES
├── folder_drop.py       # S3 / Azure Blob / local fs
├── sftp.py
├── teams_webhook.py
└── slack.py
```

**Schema:**
```sql
CREATE TABLE delivery_subscriptions (
  subscription_id UUID PRIMARY KEY,
  org_id          UUID NOT NULL,
  user_id         UUID,
  scope           TEXT,        -- 'rfp' | 'all_my_rfps' | 'department'
  scope_id        TEXT,
  channel         TEXT,        -- 'email' | 'folder' | 'teams' | 'sftp' | 'slack'
  target          JSONB,
  trigger         TEXT,        -- 'on_complete' | 'on_block' | 'both'
  enabled         BOOLEAN DEFAULT true
);

CREATE TABLE delivery_attempts (
  attempt_id      UUID PRIMARY KEY,
  subscription_id UUID,
  run_id          UUID,
  attempted_at    TIMESTAMPTZ DEFAULT now(),
  status          TEXT,
  error           TEXT,
  next_retry_at   TIMESTAMPTZ,
  UNIQUE (subscription_id, run_id, trigger)   -- idempotency
);
```

**Flow:** on `run.complete` or `run.blocked`, find matching subscriptions, dispatch, log attempt. Failed attempts re-queued via existing `app/infra/rate_limiter.py` exponential backoff.

**API:** `POST /api/v1/evaluate/start` accepts `deliver_to: [...]` for one-shot delivery; `POST /api/v1/subscriptions` for persistent subscriptions.

### Files
- [app/delivery/](app/delivery/) (new module), [app/db/schema.sql](app/db/schema.sql), [app/api/evaluation_routes.py](app/api/evaluation_routes.py), [app/jobs/delivery_dispatcher.py](app/jobs/) (new), [app/pipeline/nodes.py](app/pipeline/nodes.py), [tests/test_delivery.py](tests/) (new).

### Exit / pass criteria — Phase 8
- [ ] `app/delivery/base.py` defines `DeliveryChannel` ABC with `dispatch(run_id, pdf_bytes, summary, target) -> DeliveryResult`.
- [ ] At minimum `email_smtp.py` and `folder_drop.py` implementations exist and pass their integration tests.
- [ ] `delivery_subscriptions` and `delivery_attempts` tables exist with the UNIQUE constraint preventing duplicate delivery.
- [ ] Integration test using `mailhog` (local SMTP catcher): subscribe with channel=email, run smoke evaluation, assert email arrives with PDF attachment and plain-text summary body.
- [ ] Integration test: subscribe with channel=folder targeting local `/tmp/delivery-test/`, assert PDF written to that path on run completion.
- [ ] Delivery failure test: configure invalid SMTP creds → `delivery_attempts.status='failed'` row appears with `next_retry_at` set; eventually succeeds after creds are fixed.
- [ ] Idempotency test: trigger the same `run.complete` event twice; only ONE delivery occurs (UNIQUE constraint rejects duplicate).
- [ ] One-shot delivery: `POST /api/v1/evaluate/start` with `deliver_to=[{"channel":"email","target":"x@y"}]` creates a transient subscription scoped to that run only; subscription auto-deleted after delivery success.
- [ ] `tests/test_delivery.py` passes in CI.

---

## Phase 9 — Multi-user RFP visibility & collaboration

### Intent
Real organisations have multiple RFPs running concurrently across departments. Without proper visibility, the system can only ship to single-user-per-customer demos. This is the table-stakes feature for enterprise sales.

### Critical invariant — access is inherited from the RFP, not derived at ingestion time

When vendor files arrive autonomously (Phase 5 watchers), the ingestion pipeline must **NEVER** try to determine "which user should see this file." User-level access is fully decided when the RFP is created (T0); file arrival (T1) only adds data into an already-permissioned slot.

- `evaluation_runs.created_by_email` and `creator_dept_id` are copied from `rfps.*` at run creation — never re-derived from the file.
- `rfp_collaborators` and `approval_assignments` are joined at visibility-check time — not copied per-file.
- Ingestion writes `extracted_facts(rfp_id, vendor_id, ...)`. It writes no user identifiers.
- Autonomous attribution must verify `invited_vendors` membership before ingesting. Uninvited vendors → admin queue, never silently ingested.

### Schema
```sql
-- Matrix membership
CREATE TABLE user_departments (
  user_id        UUID,
  department_id  UUID,
  role_in_dept   TEXT,    -- 'member' | 'lead' | 'observer'
  PRIMARY KEY (user_id, department_id)
);

-- Explicit invite-a-reviewer
CREATE TABLE rfp_collaborators (
  run_id     UUID,
  user_id    UUID,
  role       TEXT,        -- 'viewer' | 'reviewer' | 'editor'
  added_at   TIMESTAMPTZ,
  added_by   UUID,
  PRIMARY KEY (run_id, user_id)
);

-- Approval queue
CREATE TABLE approval_assignments (
  run_id            UUID,
  approver_user_id  UUID,
  approver_role     TEXT,   -- 'cfo' | 'cto' | 'cpo' | 'legal'
  status            TEXT,   -- 'pending' | 'approved' | 'rejected'
  assigned_at       TIMESTAMPTZ,
  resolved_at       TIMESTAMPTZ,
  comment           TEXT,
  PRIMARY KEY (run_id, approver_user_id)
);
```

### Visibility function — default-deny
```sql
CREATE FUNCTION runs_visible_to(p_user_id UUID, p_user_email TEXT,
                                p_user_role TEXT, p_org_id UUID)
RETURNS SETOF evaluation_runs AS $$
  SELECT r.* FROM evaluation_runs r
  WHERE r.org_id = p_org_id
    AND (
      p_user_role IN ('platform_admin', 'company_admin')
      OR r.created_by_email = p_user_email
      OR r.creator_dept_id IN (SELECT department_id FROM user_departments WHERE user_id = p_user_id)
      OR EXISTS (SELECT 1 FROM rfp_collaborators WHERE run_id = r.run_id AND user_id = p_user_id)
      OR EXISTS (SELECT 1 FROM approval_assignments WHERE run_id = r.run_id AND approver_user_id = p_user_id)
    );
$$ LANGUAGE SQL STABLE;
```

### API
```
GET /api/v1/runs?scope=mine | department | approvals | shared | all
POST /api/v1/runs/{run_id}/collaborators  → invite
POST /api/v1/admin/user-departments       → matrix membership
POST /api/v1/admin/approval-assignments   → approval routing
```

### UI tabs (permission-aware)
```
| My RFPs (3) | IT Department (12) | Pending Approval (1) | Shared with me (5) | All (admin only) |
```

### Files
- [app/db/schema.sql](app/db/schema.sql), [app/auth/rbac.py](app/auth/rbac.py), [app/domain/visibility.py](app/domain/) (new), [app/api/evaluation_routes.py](app/api/evaluation_routes.py), [app/api/admin_routes.py](app/api/admin_routes.py), `frontend/app/dashboard/page.tsx`, `frontend/components/CollaboratorPicker.tsx` (new), [tests/test_visibility_matrix.py](tests/) (new).

### Exit / pass criteria — Phase 9
- [ ] All 3 new tables (`user_departments`, `rfp_collaborators`, `approval_assignments`) exist.
- [ ] `runs_visible_to()` SQL function exists and is unit-tested with the 5-persona matrix:
  - Admin sees all 6 fixture RFPs.
  - IT dept_user sees own + IT department runs only.
  - HR dept_user sees own + HR runs; does NOT see IT runs (default-deny verified).
  - Invited reviewer sees only the RFP they were invited to.
  - Approver sees only RFPs they have pending `approval_assignments` on, across all departments.
- [ ] `GET /api/v1/runs?scope=mine|department|approvals|shared|all` returns scoped lists correctly per the matrix.
- [ ] `GET /api/v1/runs?scope=all` returns HTTP 403 for any non-wide-role user.
- [ ] Dashboard tab counts match the underlying scope endpoint counts (integration test against fixture data).
- [ ] **Invariant test:** start with a clean user/access state; trigger autonomous ingestion (Phase 5) for an RFP; assert no new rows in `rfp_collaborators` / `user_departments` / `approval_assignments` were created by the ingestion path.
- [ ] Off-boarding test: disable a user account; assert they can no longer access RFPs they previously created (HTTP 401 on the visibility endpoint).
- [ ] Invite flow: `POST /api/v1/runs/{run_id}/collaborators` with `{user_id, role}` makes the RFP appear in that user's "Shared with me" tab; integration tested.
- [ ] `tests/test_visibility_matrix.py` covers all 5 personas and is green in CI.

---

## Phase 10 — Architecture rationale doc + 4-layer mapping spec

### Intent
Sales / customer-facing teams need an authoritative, repo-grounded answer to "why a chain of agents instead of one LLM?" — and a precise specification of how vendor responses map back to RFP requirements (the four-layer mapping). These belong in the repo, not in conversations and slack threads.

### Deliverables

**`docs/ARCHITECTURE_RATIONALE.md`** (~500 words) — five reasons in priority order, each with a concrete code reference:

1. **Context window** — 15 vendors × 50 pages ≈ 2M tokens; Claude Opus 4.7 caps at 1M. Cite line in [app/pipeline/nodes.py](app/pipeline/nodes.py).
2. **Grounding & audit trail** — every `extracted_facts` row has `grounding_quote` + `source_chunk_id` + `source_page`. Show example schema row.
3. **Deterministic business rules** — approval-tier logic in `app/agents/decision.py` is Python, not LLM. Show snippet.
4. **Cost & latency** — multi-agent uses cheap models for cheap tasks; single Opus call on 2M tokens ≈ $30+, pipeline ≈ $2.
5. **Failure isolation + self-correction** — Phase 2 critic + retry budgets per agent. Reference critic_router.

**`docs/RFP_RESPONSE_MAPPING.md`** (the four-layer mapping spec):

| Layer | What | Where |
|---|---|---|
| 1. Identity | which RFP / which vendor | `vendor_documents.rfp_id` + `.vendor_id` |
| 2. Semantic | which RFP question → which vendor answer | `extracted_facts.extraction_target_id` ↔ `evaluation_setups.scoring_criteria[].extraction_target_ids` |
| 3. Page-level | which page of which file | `extracted_facts.source_chunk_id` + `.source_page` + `.source_filename` |
| 4. Verbatim | the exact sentence quoted | `extracted_facts.grounding_quote` |

Include SQL examples for: "which RFP questions did vendor X NOT answer?", "show me Acme's SLA answer with citation", "list all unanswered mandatory checks".

### Files
- `docs/ARCHITECTURE_RATIONALE.md` (new), `docs/RFP_RESPONSE_MAPPING.md` (new), [README.md](README.md), [CLAUDE.md](CLAUDE.md).

### Exit / pass criteria — Phase 10
- [ ] `docs/ARCHITECTURE_RATIONALE.md` exists, word count ≤ 500.
- [ ] All 5 reasons present; each links to a concrete code file/line as evidence.
- [ ] `docs/RFP_RESPONSE_MAPPING.md` exists with the four-layer table and at least 3 worked SQL examples.
- [ ] Both docs linked from the top of README.md and from CLAUDE.md "Project documentation" section.
- [ ] Non-engineer review test: a procurement person from outside the team reads `ARCHITECTURE_RATIONALE.md` and can articulate at least 3 of the 5 reasons in their own words.

---

## Cross-phase critical files map

| File | Touched in phases |
|---|---|
| [app/providers/llm.py](app/providers/llm.py) | 1, 3 |
| [app/pipeline/state.py](app/pipeline/state.py) | 2, 4 |
| [app/pipeline/graph.py](app/pipeline/graph.py) | 2, 4, 6 |
| [app/pipeline/nodes.py](app/pipeline/nodes.py) | 2, 4, 5, 8 |
| [app/pipeline/critic_router.py](app/pipeline/) (new) | 2 |
| [app/pipeline/ingestion_graph.py](app/pipeline/) (new) | 5 |
| [app/pipeline/incremental_runner.py](app/pipeline/) (new) | 6 |
| [app/agents/explanation.py](app/agents/explanation.py) | 1, 2, 7 |
| [app/prompts/explanation/generate_narrative.yaml](app/prompts/explanation/generate_narrative.yaml) | 1 |
| [app/schemas/schema_decision.py](app/schemas/schema_decision.py) | 1, 7 |
| [app/db/schema.sql](app/db/schema.sql) | 3, 5, 6, 8, 9 |
| [app/db/fact_store.py](app/db/fact_store.py) | 5, 6 |
| [app/auth/rbac.py](app/auth/rbac.py) | 9 |
| [app/domain/visibility.py](app/domain/) (new) | 9 |
| [app/domain/rfp.py](app/domain/rfp.py) | 6 |
| [app/api/evaluation_routes.py](app/api/evaluation_routes.py) | 6, 7, 8, 9 |
| [app/api/admin_routes.py](app/api/admin_routes.py) | 5, 9 |
| [app/jobs/](app/jobs/) | 5, 8 |
| [app/delivery/](app/delivery/) (new) | 8 |
| [app/output/](app/output/) | 7 |
| [deploy/modal.py](deploy/modal.py) | 5 |
| [tools/smoke_test_graph.py](tools/smoke_test_graph.py) | 1, 3, 4 |
| `tests/test_*` (new files) | per-phase |
| `docs/` | 10 |

## Existing helpers to reuse (do NOT duplicate)

- [`critic_after_explanation`](app/agents/critic.py#L437) — keep as the verdict function; `explanation_critic_node` just wraps it with routing logic.
- [`verify_grounding`](app/agents/explanation.py#L26) — already whitespace-normalised; unchanged.
- [`_route_after`](app/pipeline/graph.py#L44) — pattern for conditional routing; copy this shape for new critic routes.
- [`_emit` / `_db_append_event`](app/pipeline/nodes.py#L48) — event-emission infrastructure; reuse for critic_node, ingestion_node, delivery_dispatcher so SSE stream stays consistent.
- [`call_with_backoff`](app/infra/rate_limiter.py) — already exists; reuse for delivery retry logic, not a new implementation.
- [`require_run_access`](app/auth/rbac.py#L25) — extend to call `runs_visible_to()` rather than reimplementing.

## Cross-phase risks and mitigations

| Risk | Mitigation |
|---|---|
| Anthropic determinism is imperfect even with `temperature=0` (no `seed` support). | Documented in Phase 10 rationale. Rely on Phase 3 cache for bit-exact replay on Anthropic. Recommend OpenAI for production determinism. |
| `temperature=0` somewhere we currently rely on creative variation. | Audit every `call_llm(` callsite during Phase 1. If any callsite legitimately needs temperature>0, keep it explicit with an inline rationale comment. |
| Critic loop drives up LLM cost. | Hard cap at 2 retries (3 attempts). Cost tracker alerts if average run cost rises >20% post-Phase 2. |
| `make_critic_node` over-abstracts before pattern stabilises. | Build it AFTER Explanation works in 2a, not before. |
| Cache returns stale responses after prompt edits. | Cache key includes full prompt text. Editing a prompt produces a different key automatically. |
| Graph cycles trigger LangGraph recursion limit. | Bound by `*_retry_count` in state + `recursion_limit=50` on compiled graph. |
| Parallel fan-out exhausts OpenAI TPM or Qdrant connection pool. | `MAX_VENDOR_CONCURRENCY=5` semaphore in Phase 4. |
| Background ingestion silently ingests files for uninvited vendors. | Phase 5a `invited_vendors` membership check; uninvited → admin queue. |
| Vendor sees another vendor's data via folder-permission leak. | Filesystem permissions on `drops/{rfp_id}/` must be customer-managed. Phase 5a documentation explicitly calls this out. Cloud-storage variants (S3) inherit IAM. |
| Cross-org leakage via visibility function. | Phase 9 visibility function ALWAYS includes `r.org_id = p_org_id` as a top-level predicate. Integration test asserts no cross-org leakage with 2-org fixture. |
| Off-boarded user retains access. | Phase 9 exit criterion explicitly tests for this. |
| Addendum from uninvited vendor accepted. | Phase 5a + 5b: attribution failure → admin queue. Phase 6 ingest path uses same attribution layer. |
