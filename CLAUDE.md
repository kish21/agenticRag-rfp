# CLAUDE.md
# Read this completely at the start of every session.
# These are constraints, not suggestions.
# Last updated: 2026-05-23

---

## THIS PROJECT

**Product:** Enterprise Agentic AI Platform — RFP Evaluation Agent (first agent)
**Architecture:** 9-agent multi-agent system with structured outputs and critic guardrails
**Tech stack finalised:** LangGraph + LlamaIndex + Qdrant + BGE CrossEncoder reranker (swappable to Cohere/ColBERT) + PostgreSQL + FastAPI + Modal + LangSmith + LangFuse + Next.js

---

## THE NINE AGENTS — DO NOT MERGE, DO NOT SKIP

```
1. Planner Agent       — decomposes evaluation into typed task DAG            [Skill 02]
2. Ingestion Agent     — LlamaIndex → Qdrant, triggers Extraction at ingestion [Skill 03]
3. Retrieval Agent     — hybrid search + BGE CrossEncoder reranker + HyDE       [Skill 03b]
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
| `azure` | Azure OpenAI | Uses AzureAsyncOpenAI client |
| `modal` | Qwen 2.5 72B AWQ via vLLM on Modal A100 | OpenAI-compatible endpoint, no per-token cost |

Agents call `call_llm()` — never import provider SDKs directly in agent files.
Embeddings are configurable via EMBEDDING_PROVIDER (openai/azure/local/modal) — no longer hardwired to OpenAI.

## MODAL DEPLOYMENT

Two deployment surfaces:
- **FastAPI** (local or any cloud): real-time API, agent orchestration, retrieval
- **Modal** (`app_modal.py`): PDF extraction (CPU), batch embeddings (A10G), LLM inference — Qwen 2.5 72B AWQ (A100-80GB), scheduled cleanup/rate monitoring

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

**Current skill:** Phase 3 + Phase 5 done 2026-05-29. 2026-05-30: docs refresh (#172), real BM25/P1.12 (#173), Phase 7 plan align (#174), **Phase 7 customer report (#176)** + polish (#177) + **frontend report buttons (#178)**, **Phase 8a delivery channels (#179)** + **delivery service facade (#181)** + decomposition (#182), **Phase 2c exit-criteria contract (#183)** + **self-correcting retry engine (#184)**, P0/P1/P2 code-review fixes (#188), **Phase 2c wiring COMPLETE + merged (#189)**, **P0.16 tenant isolation / RLS now enforces + merged (#190)** + CI lint fix (#191). Phase 1, 2, 2c, 4, 7, 9 on master; Phase 8 module foundation on master. Enterprise-readiness: **E1 DONE**, **E2 DONE+merged (#193)**, **E3 evidence benchmark DONE+merged (#195)**, **E3.a extraction-recall correction merged (#196)**, **prompt-source local-authoritative merged (#197)**. **E3.b (contradiction handling) WIP on DRAFT PR #198** (branch `e3b-contradiction-insufficient`). 🔴 **TOP PRIORITY next: scoring evidence-starvation** (real vendors score ~0.2-0.3/10 — see NEXT SESSION PLAN). Remaining: E3.a/b residuals, E3.c-g, 6, 8b, 10.
**Last verified checkpoint:** **E3 — Evidence-quality benchmark ~80% DONE** on branch `e3-evidence-benchmark` (PR pending). Built a repeatable ground-truth benchmark in `benchmark/` (golden_schema + generation + 6 synthetic scenarios with answer keys grounded by construction + pure metrics library + runner + committed results). Contract `docs/dev/E3_EXIT_CRITERIA.md` (baseline-first, scanned deferred — both signed off). **Measured baseline (gpt-4o):** grounding/citation accuracy **1.00**, **0 fabricated**, retrieval recall 1.00, score-consistency stdev 0.0. **No-forced-scores shipped** (`CriterionScore.insufficient_evidence`): evaluation no longer fabricates a 0 when evidence is absent — flagged + surfaced in decision/comparator/explanation + a compare-page UI badge (`forced_when_insufficient` 5→1, insufficient-rate 0.00→0.80). Tests: `tests/test_benchmark_dataset.py` (A1/A2/A3, 9) + `tests/test_benchmark_metrics.py` (11) + `tests/test_insufficient_evidence.py` (2); **full suite 231 green**; contracts 14/14; drift OK. Open follow-ups logged as E3.a–f (extraction recall ~0.60, contradiction→insufficient, missing-mandatory→reject, coverage-normalised ranking, regression gates, scanned/OCR). UI via `/frontend-design`+`/anti-ai-ui`.

<details><summary>E2 — Auth hardening DONE + merged (#193, commit 1c7bc4a)</summary> Shipped: env-aware `cookie_secure` (True in prod/staging, `COOKIE_SECURE` override) in `app/config/loader.py`; **one account per email** (chose platform-wide `UNIQUE(email)`) — `signup` 409 on dup, `_ensure_dev_user` now `ON CONFLICT (email)`; **session allowlist** `auth_sessions` keyed by token `jti` (added to JWT in `app/auth/jwt.py`) — `get_current_user` + the cookie-only SSE stream (`evaluation_routes.py`) reject revoked/missing sessions, **fail-closed**; logout revokes this jti, password-reset revokes all (`app/auth/sessions.py`); **one-time hash-at-rest expiring tokens** `auth_onetime_tokens` for invite-accept + password-reset (`app/auth/tokens.py`), **no endpoint returns a plaintext/temp password**; 8-char min password. schema.sql + Alembic `0012`. Reviewer note `docs/dev/AUTH_HARDENING.md`. Tests `tests/test_auth_hardening.py` (13, incl. dev-seed-txn regression); **full suite 209 green** locally vs live Postgres; **CI green** (fresh schema.sql bootstrap confirms FORCE-RLS+grants on the 2 new tables); contracts 14/14; drift OK. Self-reviewed via `/code-review high` — fixed 3 confirmed findings (dev-seed `db.begin()` autobegin bug, SSE revocation bypass, fail-closed lookup).</details>
**Next action (2026-06-01):** (1) `/code-review` the E3.b DRAFT PR #198 (branch `e3b-contradiction-insufficient`) — it has NOT been reviewed yet. (2) Then attack **scoring evidence-starvation** (the day's big finding — see NEXT SESSION PLAN). Lower priority: E3.b.1 cert status-conflict, E3.b.2 grader mapping, E2 auth follow-ups, 8b.
**Blockers:** none. **Uncommitted:** none — all pushed. Local DB (docker `platform_postgres`/`platform_qdrant`) was up today; `PROMPTS_USE_HUB` unset so local YAML prompts are authoritative.

### NEXT SESSION PLAN (set 2026-05-31 — START HERE)  ·  (the Phase-2c plan below is OBSOLETE — Phase 2c merged #189)

**Step 0:** `/code-review` the E3.b DRAFT PR **#198** (it is unreviewed). Then merge if green, or fix findings.

**🔴 Step 1 — THE BIG FINDING: scoring evidence-starvation.** On the REAL fixtures (`data/documents/` — RFP + Acme/ClearPath + Apex + the criteria CSV), the full pipeline runs end-to-end **but both real vendors score only ~0.2-0.3/10 ("marginal", requires_human_review)**. Root cause (verified by reading the smoke artifact `tests/smoke_results/<latest>/`): the **Evaluation Agent scores from EXTRACTED facts (PostgreSQL), not the proposal text** (by architecture), so scoring quality is capped by extraction. On real docs extraction distils each criterion to ~1 thin fact (and missed Acme's SLAs entirely → that criterion went `insufficient`), so good vendors look bad. This is NOT a calc bug and NOT introduced by E3.b — it's the agentic extract-then-score design + low extraction recall. **This is likely why "it scored well before agentic" (older path scored against richer text).**
  - **Two levers (do these):** (a) **E3.a — extraction recall** (capture more per criterion); (b) **a chunk-fallback for SCORING criteria** — mandatory checks already re-retrieve chunks when facts are missing (`_evaluate_mandatory_check` `should_fallback`); scoring criteria (`_score_criterion`) do NOT — add the same, so a thin/empty criterion scores against retrieved chunks instead of collapsing to insufficient/0.
  - Likely also a **display bug**: total shown as `X/10` but appears to be on a 0-1 scale (0.30 ≈ 30% ≈ 3/10). Verify `total_weighted_score` scaling in decision/report.

**Step 2 (lower):** E3.b.1 cert status-conflict (one cert, one status — needs schema way to represent contradicted status); E3.b.2 benchmark grader can't read retried-eval results (`state_to_actual` reads `evaluation_output_objects`, cleared from final state after the evaluation critic-retry — find where the retried result lands). Then E3.c-g, E2 auth follow-ups, 8b.

**How to reproduce today's real-doc run:** `python tools/smoke_test_graph.py --rfp data/documents/RFP_IT_Managed_Services_MFS_2026.pdf --criteria data/documents/Vendor_Selection_Criteria_MFS.csv --vendor-pdf data/documents/Acme_ClearPath_Proposal.pdf --vendor-pdf data/documents/nightbuilb_Apex_Technology_Proposal.pdf` (needs docker postgres+qdrant up). Benchmark: `python -m benchmark.runner.run_benchmark`.

**Wiring steps (all offline-testable):**
1. Add `critic_feedback: str = ""` to `run_extraction_agent` ([app/agents/extraction.py](app/agents/extraction.py)) + `run_evaluation_agent` ([app/agents/evaluation.py](app/agents/evaluation.py)); inject a "PREVIOUS ATTEMPT FAILED…" preamble into their prompts (mirror [app/agents/explanation.py](app/agents/explanation.py) `_generate_vendor_narrative`).
2. Add `critic_metrics_accum: Annotated[dict, _merge_dicts]` to `PipelineState` ([app/pipeline/state.py](app/pipeline/state.py)).
3. Route `extraction_per_vendor` + `evaluation_per_vendor` ([app/pipeline/nodes.py](app/pipeline/nodes.py)) through `app.pipeline.critic_retry.run_with_critic_retry(...)` with stage-specific `build_feedback`; remove the current inline-only handling (Extraction has NO block-guard today; Evaluation HARD-blocks at nodes.py:489). Aggregate telemetry into `summary.json`.
4. Tests vs #183 criteria → `/phase-done-rfp` (Checks A topology + C per-vendor guards) → update `PERFORMANCE_AND_QUALITY_METRICS.md` claim (Critic-as-controller at the 3 generation steps; assisted/deterministic steps validation-only, by design) → PR.

**Also pending (separate, lower priority):**
- **Phase 8b wiring** — delivery completion hook + Mode C auto-trigger. Engine/channels done (#179/#181); needs live infra + Mailtrap/Resend SMTP creds. Email works today via the SMTP channel + `.env` (Mailtrap sandbox or Resend free 3k/mo). 8c (subscription/dispatcher engine) + 8d (Teams/Slack + in-app notifications) are customer-driven.

**Deliberately NOT doing (each has a reason)**
- Phase 6 (incremental re-eval for addenda) — wait for a customer who actually sends addenda
- Phase 10 (architecture doc) — `/doc-create --doc-type architecture --audience cto` in a future doc session
- Modal cron deploy — $5-15/month for zero benefit until a real `auto_to_evaluate` customer

### Deferred items tracked in BACKLOG.md
- P2.0 — Phase 5 D1 (Modal cron dashboard), D4 (5-vendor parallel wall-clock), E1 (≤60s user-evaluate wall-clock) — live integration
- P2.0a — Phase 5 legacy-table FK refactor
- P2.0b — Phase 3 3.17 live cost-savings benchmark (added 2026-05-29 post-audit)
- P2.0c — Phase 2c finish critic-as-controller for Extraction + Evaluation (added 2026-05-29)

### Phase 5 highlights now on master
- 4 new tables: `rfps`, `invited_vendors`, `ingestion_jobs`, `event_log`
- RFP creation API at `/api/v1/rfps/...`; UI at `/procurement/rfps/new`
- Background watcher (`app/jobs/ingestion_watcher.py`) + LLM-fallback attribution (`app/jobs/llm_attribution.py`)
- Modal-cron deadline scheduler (`app/jobs/deadline_processor.py`) + ingestion sub-graph (`app/pipeline/ingestion_graph.py`) — registered in `deploy/modal.py::phase5_deadline_tick`, NOT yet deployed (cost decision pending)
- Pipeline short-circuit on user-triggered Evaluate (`app/pipeline/nodes.py`)
- Admin endpoints for attribution queue + late-addendum acceptance (`app/api/admin_routes.py`)
- CI now provisions a postgres service and bootstraps from `schema.sql` + `alembic stamp head` so the 47 new DB-touching tests run on every PR

### Phase 3 highlights now on master
- New table `llm_response_cache` (Alembic `0007`); tenant-blind by design
- `call_llm()` wrapped with `use_cache` + `cache_bust`; cache hits never instantiate the provider SDK client
- `RunCostAccumulator` extended with `cache_hits` / `cache_misses` / `cache_hit_rate` / `cache_savings_usd`
- Customer-safety endpoints: `POST /api/v1/evaluate/{run_id}/rerun?bypass_cache=true` (with `divergence_flag` if results differ); `DELETE /api/v1/admin/llm-cache` (audit-logged)
- `tools/smoke_test_graph.py --no-cache` + `--compare-with-prior <dir>` byte-identity check
- README "LLM Caching (Phase 3)" section documents the 3 escape hatches

---

## SESSION START — MANDATORY BEFORE ANY CODE

```bash
python tools/checkpoint_runner.py status
python tools/drift_detector.py
python tools/contract_tests.py
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

## FRONTEND DESIGN RULES — ENFORCE ON EVERY UI TASK

### Stack
- **Framework:** Next.js 16 App Router, React 19, Tailwind CSS v4
- **Dev server:** `cd frontend && npm run dev` → http://localhost:3000
- **Theme system:** CSS custom properties on `<html>` via `applyThemeVars()` in `frontend/lib/theme.ts`
- **Font:** Plus Jakarta Sans (loaded via `next/font/google`, weights 300–800, variable `--font-jakarta`). Mono: JetBrains Mono (`--font-mono-loaded`). Constants: `FONT`, `DISPLAY`, `MONO` from `@/lib/theme`
- **51 themes** selectable at runtime — never hardcode a hex colour that should theme

### Reference Images
- If a reference image is provided: match layout, spacing, typography, and color **exactly**. Do not improve or add to the design.
- If no reference image: design from scratch using the guardrails below.
- After writing UI code, describe what you expect to see. If a screenshot is taken, compare pixel-by-pixel: spacing, font weight, exact colors, border-radius, alignment. Fix mismatches.

### Brand Assets
- Check `frontend/public/` before designing. Use any logos, icons, or brand images found there.
- No brand_assets folder exists yet — do not use placeholder images unless explicitly needed.
- Platform name: **"Meridian AI Platform"** · Company: **"Meridian Financial Services"**
- Colors come from the active theme CSS vars — never invent brand colors outside the theme system.

### CSS Variable Rules — NEVER BREAK
- **Never write a raw hex colour** in any component (e.g. `"#1A2540"`). Always use `var(--color-*)`.
- **Never write a raw font string** (e.g. `"'IBM Plex Sans', sans-serif"`). Always use `FONT`, `DISPLAY`, or `MONO` from `@/lib/theme`, or `var(--font-sans)` / `var(--font-display)` / `var(--font-mono)`.
- Inline styles that bypass CSS vars cannot respond to theme changes — they will look broken on non-default themes.
- Exception: `AgentSwitcherRail` sidebar is intentionally hardcoded dark — do not change.

### Typography Rules (matching top SaaS products: Linear, Stripe, Vercel)
- **One font family only: Plus Jakarta Sans.** No Inter, Georgia, Times, IBM Plex, or system-ui as primary.
- Headings use `DISPLAY` (`var(--font-display)`), `fontWeight: 800`, `letterSpacing: "-0.03em"`
- Subheadings / section labels use `FONT`, `fontWeight: 600–700`, `letterSpacing: "-0.01em"`
- Body text uses `FONT`, `fontWeight: 400–500`, `lineHeight: 1.6`
- Data / timestamps / IDs use `MONO` (`var(--font-mono)`), `fontWeight: 400–500`
- Never use the same weight for a heading and its subtitle — minimum 200 weight difference

### Anti-Generic Design Guardrails
- **Colors:** Never use default Tailwind palette names (indigo-500, blue-600, etc.). Use `var(--color-accent)`, `var(--color-success)`, etc.
- **Shadows:** Never use flat `shadow-md`. Use themed shadows: `var(--shadow-sm)`, `var(--shadow-md)`, `var(--shadow-lg)`.
- **Gradients:** Use `var(--bg-gradient)` for page backgrounds. Cards can use subtle accent-tinted gradients.
- **Animations:** Only animate `transform` and `opacity`. Never `transition: all`. Use `var(--transition)` for duration.
- **Interactive states:** Every clickable element needs hover + focus-visible + active states. Use `var(--color-surface-hover)` for hover backgrounds.
- **Spacing:** Use consistent increments (4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56) — not arbitrary values.
- **Depth / layering:** base (`var(--color-background)`) → elevated (`var(--color-surface)`) → floating (`var(--shadow-lg)` + border). Never all at same z-plane.
- **Borders:** Use `var(--color-border)` for default, `var(--color-border-strong)` for emphasis. Radius from `var(--radius)`.
- **Status colors:** Always semantic — `var(--color-success)` / `var(--color-warning)` / `var(--color-error)` / `var(--color-info)`.

### Hard Rules
- Do not mix `border` shorthand with `borderTop` / `borderLeft` etc. in React inline styles — React will warn and style breaks on re-render. Use all four sides explicitly.
- Do not use `transition-all` or `transition: all` anywhere.
- Do not hardcode dark/light mode logic per-component. Use `isDark` from `useThemeContext()` (not the legacy `useTheme()` from TopBar).
- Do not load additional Google Fonts via `@import url(...)` in component CSS strings. Plus Jakarta Sans and JetBrains Mono are already loaded globally via `next/font`.
- Do not add sections, features, or content not in the reference image.
- Do not "improve" a reference design — match it exactly.

---

## PACKAGE STRUCTURE — app/ sub-packages (refactored May 2026)

```
app/core/ is GONE — replaced by focused sub-packages:

app/auth/        — jwt.py, rbac.py, dependencies.py
app/providers/   — llm.py, embedding.py, reranker.py, compute.py, observability.py
app/infra/       — audit.py, logger.py, rate_limiter.py, circuit_breaker.py, cost_tracker.py
app/retrieval/   — qdrant.py, pipeline.py
app/domain/      — criteria.py, rfp.py, override.py, org_settings.py, agent_registry.py
app/schemas/     — output_models.py
app/validators/  — extraction.py, retrieval.py, ingestion.py
app/agents/      — flat: 9 single .py files, one per agent
app/api/         — routes per concern
app/jobs/        — cleanup.py, rate_monitor.py
deploy/          — modal.py (was app_modal.py)
tools/           — checkpoint_runner.py, contract_tests.py, drift_detector.py
```

Import rule: never import from app.core (deleted). Use the sub-package paths above.

## FILE OWNERSHIP MAP

```
Skill 01: requirements.txt, .env, docker-compose.yml, app/config/ (loader.py + platform.yaml + product.yaml), app/main.py
Skill 02: app/agents/planner.py, app/agents/critic.py
          app/retrieval/qdrant.py, app/infra/rate_limiter.py
          app/api/auth_routes.py, app/api/evaluation_routes.py, deploy/modal.py
Skill 03: app/agents/ingestion.py, app/retrieval/pipeline.py
          app/validators/ingestion.py
Skill 03b: app/agents/retrieval.py, app/providers/reranker.py
           app/retrieval/pipeline.py
Skill 04: app/agents/extraction.py, app/schemas/output_models.py
          app/db/schema.sql, app/db/fact_store.py
Skill 05: app/agents/evaluation.py, app/agents/comparator.py
Skill 06: app/agents/decision.py, app/agents/explanation.py
          app/domain/override.py, app/domain/rfp.py
Skill 07: app/output/pdf_report.py, frontend/ (Next.js)
          tests/regression/
Skill 08: app/providers/observability.py, app/jobs/cleanup.py
          app/jobs/rate_monitor.py
Skill 09: app/domain/agent_registry.py, app/api/admin_routes.py
          app/agents/hr_agent_config.py
```

---

## SESSION END — MANDATORY

```bash
python tools/checkpoint_runner.py status
python tools/drift_detector.py
```

Update four fields above. Add one line to .claude/daily_build_log.md.

---

## VERIFIED PACKAGE VERSIONS — May 2026 (grounded from requirements.txt)

```
openai==2.33.0          langchain==1.2.16       langgraph==1.1.10
langsmith==0.8.0        langfuse==4.5.1         llama-index-core==0.14.21
qdrant-client==1.17.1   cohere==5.21.1          sentence-transformers==4.1.0
fastapi==0.136.1        pydantic==2.13.3        sqlalchemy==2.0.40
uvicorn[standard]==0.34.3  psycopg2-binary==2.9.10  httpx==0.28.1
```

NOTE: langgraph 1.1.10 is installed (not 0.4.x as in skill files). The StateGraph API
is compatible but import paths changed. When building the LangGraph pipeline in Skill 07,
use:
    from langgraph.graph import StateGraph, END
    from langgraph.graph.state import CompiledStateGraph
Do not use deprecated 0.x import paths.

**Critical API changes — will break if wrong version used:**
- `langfuse` 2.x → 4.x: SDK rewritten — read migration guide before Skill 08
- `cohere`: `cohere.Client()` deprecated → use `cohere.ClientV2()`
- `qdrant-client`: `client.search()` deprecated → use `client.query_points()`
- `pydantic`: `@validator` deprecated → use `@field_validator` (all skill code uses v2 style)
- `ragatouille`: removed from requirements — unmaintained, use sentence-transformers CrossEncoder

---

## KNOWN FIXES — DO NOT REVERT

### PDF whitespace normalisation fix (May 2026)

PDF table parsing produces cells on separate lines.
The LLM joins them with single spaces when quoting.
The verbatim grounding check must normalise whitespace
before comparing.

Fix applied in:
  app/agents/extraction.py — _hallucination_risk()
  app/agents/critic.py — critic_after_extraction()

Pattern: re.sub(r'\s+', ' ', text).strip() before
string containment check.

This fix applies to all fact types. Do not revert.
Do not add raw \n matching to grounding checks.
