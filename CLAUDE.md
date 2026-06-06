# CLAUDE.md
# Read this completely at the start of every session.
# These are constraints, not suggestions.
# Last updated: 2026-06-05

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
- **Modal** (`deploy/modal.py`): PDF extraction (CPU), batch embeddings (A10G), BGE CrossEncoder reranking (A10G, `RERANKER_PROVIDER=modal` — dev/prod call one shared model), LLM inference — Qwen 2.5 72B AWQ (A100-80GB), scheduled cleanup/rate monitoring

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

**Last updated:** 2026-06-06 · **Branch:** master (clean, synced with origin) · **HEAD:** `450fc04` (+ DX-001 #128 PR pending)

**On master — all merged.** Phases 1, 2, 2c, 4, 5, 7, 9 + Phase 8 module foundation. Enterprise-readiness E1–E3 + E3.a–e done. Working tree clean; nothing pending to push.

**#128 (DX-001) OpenAPI/Swagger annotations — BUILT (PR pending).** All 58 routes + `/health` now declare a `summary` + description; authenticated routes document 401, path-param routes 404/409, role-gated routes 403; app-level OpenAPI metadata (description/contact/license) + 9 per-tag descriptions are config-driven (`platform.yaml api_docs` → `PlatformApiDocs` in `loader.py`, read by `main.py _openapi_metadata()`). New reusable `app/api/openapi_responses.py` (error-spec constants + `responses()` merge) keeps the decorators DRY. **Conservative — zero new `response_model`** (the 13 existing reformatted only; snapshot guard pins all 19 model-bound routes), so no JSON body can be filtered. `/metrics` moved to `include_in_schema=False`. New tests: `tests/test_openapi_annotations.py` (hard-fail completeness + 401/404 + app-info meta-tests over `app.openapi()`) and `tests/test_openapi_response_snapshot.py` (live body snapshot, no DB). Verified: 11 new tests pass + full non-live suite **366 passed, 1 skipped**, 0 failures. Benchmark not re-run (no agent/pipeline code touched). Full detail in `docs/dev/128.md`.

**#267 (P1.7) self-consistency voting — MERGED.** Borderline mandatory checks (primary confidence in `[confidence_min, confidence_max]`, default `[0.5, 0.75]`) are resampled `samples`× (default 3) at non-zero temperature with distinct seeds; the STRICT majority wins, no-majority → fail-safe `insufficient_evidence`. Clear-cut checks (confidence outside the band) stay single-call → no added cost. New `_decide_check_with_voting` helper in `app/agents/evaluation.py` returns ONE representative parsed dict (so E3.b contradiction override + chunk fallback + `ComplianceDecision` construction are all untouched) plus a `vote_breakdown` audit dict (new defaulted field on `ComplianceDecision`). Baseline call keeps today's auto-derived seed (deliberate — see `docs/dev/P1.7.md`); only resamples take explicit seeds. Config-driven, ON by default: `platform.yaml self_consistency` (`PlatformSelfConsistency` in `loader.py`). Verified: 8 unit/integration tests + full non-live suite (336 passed) + benchmark unchanged (grounding 1.0, 0 fabricated, 0 failures, no scenario flips, $0.43).

Recent merges (full per-PR detail in git history + `docs/dev/E*.md` — do not re-paste it here):
- **#265 (#59 P1.8)** — post-synthesis prose verification. The structured `grounded_claims` were already quote-verified; the Explanation Agent's FREE-TEXT prose was not. `explanation.py verify_narrative_claims()` (2nd temperature-0 `call_llm`, prompt `explanation/verify_claims.yaml`) fact-checks each prose claim vs the same evidence (chunks + verified claims + system_facts); per-claim `ClaimVerification` + `prose_verification_score` attach to each `VendorNarrative`. `critic_after_explanation` gates it like grounding-completeness — `< block_below` HARD (existing explanation retry loop regenerates; feedback lists the bad sentences), `< warn_below` SOFT. Config-driven, ON by default: `platform.yaml synthesis_verification`. Proven: 10 mocked unit tests + a `RUN_LIVE_LLM=1`-gated live planted-hallucination test (real model flags fabrications, blocks); benchmark unchanged.
- **#256 (#133)** — prompt-injection defence at ingestion (OWASP LLM01). Config-driven scanner (`app/validators/injection.py`, patterns in `platform.yaml injection_defence`) scans untrusted vendor chunks before any LLM; a match → HARD Critic flag `prompt_injection_detected` → pipeline BLOCKED (fail-CLOSED). Trusted first-party RFP exempt (`trusted_source`). Verified 3 levels incl. live graph halt (only planner+ingestion ran, no report). Deeper `_verdict()` 'escalate' string-coupling refactor logged as BACKLOG **P2.28**. Toolkit patched: `enterprise-ai-audit` Cat-3 + `new-project` AI scaffold now cover injection (product-toolkit `fe4aec8`).
- **#239 (#215)** — Qdrant one collection per org (was per `(org,vendor)`). Cross-org isolation = physical collection boundary (security-critical, unchanged); within-org vendor separation = the `vendor_id` payload filter that already ran on every query. Live end-to-end verified.
- **#241 security-baseline finish** — #222 jose→PyJWT (PyJWT 2.13, HS256-only), #221 pytest 8→9, P2.27 per-setup retention precision. `pip-audit` gate now runs with **zero ignores**. (#242 = BACKLOG doc follow-up.)
- **#220 security baseline** — `pip-audit` CVE-scan job + dependabot + SECURITY.md + CHANGELOG; 33 pinned-dep CVEs remediated; `sentence-transformers` moved to optional `requirements-local.txt` (prod image slimmed, `bge`/`local` providers fail loud).
- **#219 (#212)** — reranker backend follows `.env RERANKER_PROVIDER` (default `modal`); fail-open-but-loud on air-gapped degrade.
- **Evidence-quality line** — #198 contradiction→insufficient, #200 contradiction→SOFT, #202 missing-mandatory→reject, #204 coverage-normalised ranking, #206 grader robustness, #207 regression gates + reranked baseline, #211/#213/#214 cleanups.

Latest benchmark baseline (`benchmark/results/`): grounding 1.00, 0 fabricated, 0 op-failures.

**Next action (next session) — pick ONE, one subtask per session:**
- **#124 OR-001** — Grafana dashboard JSON (Prometheus/Grafana already in docker-compose; just author panels). Recommended next quick win.
- **P1.4** — cancel running pipeline (1–2 days, full-stack — larger than one session)
- **P1.9 (#60)** — human feedback capture for score overrides → few-shot bank (1 day, full-stack)
- **E3.f (#209)** — scanned/OCR document support (P4 — parked; vendors send digital PDFs today, revisit when a customer submits scanned docs; the present-day safety fix = make scanned PDFs fail with a clear message instead of "No usable chunks")
- **8b** — delivery completion hook + Mode C auto-trigger (engine/channels done #179/#181; needs live infra + Mailtrap/Resend SMTP creds)

P1 GitHub issues: #133 ✅ (#256), #59 P1.8 ✅ (#265), P1.7 ✅ (#267) shipped; #128 DX-001 ✅ built (PR pending). Quick wins next: #124. Bigger (multi-session): #62 Vendor Q&A, #60 feedback bank, #136 LangSmith golden dataset.

De-prioritised: **E3.b.1** cert-status contradiction = **#210** (closed / won't-do — domain over-fitting; the generic value-contradiction path #198 already covers the real case. See [[generic_platform_no_domain_special_case]]).

**Deliberately NOT doing (each has a reason):**
- Phase 6 (incremental re-eval for addenda) — wait for a customer who actually sends addenda
- Phase 10 (architecture doc) — `/doc-create --doc-type architecture --audience cto` in a future doc session
- Modal cron deploy — $5–15/month for zero benefit until a real `auto_to_evaluate` customer

**Deferred (tracked in BACKLOG.md):** P2.0 (Phase 5 live-integration perf targets: Modal cron dashboard, 5-vendor parallel wall-clock, ≤60s user-evaluate), P2.0a (legacy-table FK refactor), P2.0b (live cost-savings benchmark), P2.0c (critic-as-controller for Extraction + Evaluation).

### How to run
- **Real-doc smoke** (3 real PDFs + CSV in `data/documents/`, needs docker postgres+qdrant up):
  `python tools/smoke_test_graph.py --rfp data/documents/RFP_IT_Managed_Services_MFS_2026.pdf --criteria data/documents/Vendor_Selection_Criteria_MFS.csv --vendor-pdf data/documents/Acme_ClearPath_Proposal.pdf --vendor-pdf data/documents/nightbuilb_Apex_Technology_Proposal.pdf`
- **Benchmark** (synthetic 6-scenario answer-key set): `PYTHONUTF8=1 python -m benchmark.runner.run_benchmark` — the `PYTHONUTF8=1` is REQUIRED on Windows (the runner prints `→`/`…` which crash cp1252 stdout).

### Recurring environment gotchas
- **fastembed cache** — the `Qdrant/bm25` sparse model lives in `%TEMP%\claude\fastembed_cache` and is CLEARED between sessions; under `HF_HUB_OFFLINE=1` (set when `SSL_VERIFY=false`) ingestion HARD-blocks ("Could not load model Qdrant/bm25"). Re-fetch once: `HF_HUB_OFFLINE=0 python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm25').embed(['x'])"`. See [[project_fastembed_cache_gotcha]].
- **Reranker** — `.env RERANKER_PROVIDER` is authoritative (default `modal`); the benchmark org is seeded to honour it. See [[project_reranker_env_dead_config]].
- **.env is user-owned** — never script-overwrite it (caused data loss 2026-06-01). Local DB creds: `POSTGRES_APP_USER=platform_app`.
- Corporate MITM proxy — `pip-system-certs` installed so Python trusts it.

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
openai==2.41.0          langchain==1.2.16       langgraph==1.1.10
langsmith==0.8.0        langfuse==4.5.1         llama-index-core==0.14.21
qdrant-client==1.18.0   cohere==5.21.1          sentence-transformers==4.1.0
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
