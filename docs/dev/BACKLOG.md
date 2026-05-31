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

## 🏢 ENTERPRISE-READINESS ROADMAP (external audit 2026-05-30, code-verified)

An external auditor produced 8 work-streams to get from "strong prototype" to "enterprise-purchasable." Each was **verified against the actual code** — the auditor's snapshot predates the 2026-05-30 work, so several items are already done. Status is honest: don't pay to rebuild what exists.

**Priority order (verified):** E1 isolation → E2 auth → E3 benchmark → E4 reports(DOCX only) → E5 approval+notify → E6 ops(load/latency) → E7 integrations → E8 positioning. Note: E8's security/benchmark briefs can't be written honestly until **E1 + E3** are actually done.

| # | Work-stream | Verified status | What's actually left |
|---|---|---|---|
| **E1** | Tenant isolation | ✅ DONE — see **P0.16** | RLS now enforces: non-superuser `platform_app` role + FORCE RLS + same-connection org context (pure-ASGI middleware). Proven by `tests/test_tenant_isolation_rls.py`; reviewer note `docs/dev/TENANT_ISOLATION.md`. |
| **E2** | Auth hardening | ✅ DONE 2026-05-31 (PR #193) | env-aware secure cookie; one-account-per-email aligned; jti session allowlist (`auth_sessions`) enforces revocation incl. SSE; one-time invite/reset tokens (`auth_onetime_tokens`); no plaintext passwords. Reviewer note `docs/dev/AUTH_HARDENING.md`; `tests/test_auth_hardening.py` (13). |
| **E3** | Evidence quality / benchmark | 🟢 ~80% DONE 2026-05-31 | repeatable ground-truth benchmark built + baseline measured (grounding **1.00**, 0 fabricated; no-forced-scores done, insufficient-rate 0.00→0.80). Open follow-ups: extraction recall ~0.60, contradiction→insufficient, missing-mandatory→reject policy. |
| **E4** | Buyer-ready reports | 🟢 ~85% DONE (#176/#178) | **only DOCX + an override-history section** remain |
| **E5** | Approval workflow | 🟡 PARTIAL | tables + assignments + override exist; missing full approve/reject/request-change actions + notifications (Phase 8) |
| **E6** | Production operations | 🟡 PARTIAL | circuit breaker + observability + rate limiter exist; missing **load tests + P50/P95/P99 latency+cost report + backup/restore + executed runbook** |
| **E7** | Enterprise integrations | 🔴 OPEN — future | no SSO/OIDC, no signed webhooks, no SharePoint import (pre-purchase requirements, not launch blockers) |
| **E8** | Product positioning | ⚪ OPEN — marketing | buyer one-pager / reviewer brief / security brief / benchmark brief / demo script — **depends on E1+E3 being true** |

### E2 — Auth hardening ✅ DONE 2026-05-31
**Shipped** (see `docs/dev/AUTH_HARDENING.md`): env-aware `cookie_secure` (True in prod/staging); **one account per email** chosen — code now agrees with `UNIQUE(email)`, duplicate signup → 409, `_ensure_dev_user` uses `ON CONFLICT (email)`; **session allowlist** `auth_sessions` keyed by token `jti` — `get_current_user` (and the cookie-only SSE stream endpoint) reject revoked/missing sessions, fail-closed; logout revokes this session, password reset revokes all; **one-time expiring hash-at-rest tokens** `auth_onetime_tokens` for invite-acceptance + password-reset — no endpoint returns a plaintext/temp password; 8-char min password. schema.sql + Alembic `0012`. Tests `tests/test_auth_hardening.py` (13).
**Follow-ups (separate):** wire real email delivery for invite/reset links (Phase 8 SMTP); rate-limit `/token` + `/password-reset/request`; schedule `purge_expired_sessions` into the cleanup cron. Latent edge (documented): a brand-new org reusing an email already invited elsewhere supersedes the older invite silently — benign under one-account-per-email.

### E3 — Evidence quality / benchmark 🟢 ~80% DONE 2026-05-31
**Built + measured.** Repeatable ground-truth benchmark (`benchmark/`): 6 synthetic scenarios (clean/table-heavy/long/short/conflicting/missing-evidence) with answer keys grounded by construction; pure metrics library + runner; committed results artifacts. Contract `docs/dev/E3_EXIT_CRITERIA.md` (baseline-first, signed off); methodology `benchmark/README.md`; baseline in `PERFORMANCE_AND_QUALITY_METRICS.md`. Tests: `tests/test_benchmark_dataset.py` (A1/A2/A3) + `tests/test_benchmark_metrics.py` (pure metric math) + `tests/test_insufficient_evidence.py`.
**Baseline (gpt-4o):** grounding/citation accuracy **1.00**, 0 fabricated; retrieval recall 1.00; score consistency stdev 0.0. **No-forced-scores DONE** — scoring criteria with no evidence now flag `insufficient_evidence` (forced 5→1, insufficient-rate 0.00→0.80); surfaced in decision/comparator/explanation + a compare-page UI badge.

**Open follow-ups (logged, not hidden):**
- **E3.a — extraction recall ~0.60**: ~37% of present facts missed by extraction (typed cert/insurance/project most often). Investigate retrieval-context → extraction prompt coverage.
- **E3.b — contradiction → insufficient**: conflicting evidence (e.g. £10M vs £2M, cert valid vs lapsed) is not resolved to `insufficient_evidence`; one criterion still scored on a contradicted fact, and conflicting mandatory accuracy is 0.00. Add contradiction detection feeding the insufficient state.
- **E3.c — missing-mandatory → reject policy**: a vendor missing a mandatory item becomes `review_required`, not rejected (rejection-correct 0.67). Decide + implement the policy.
- **E3.d — coverage-normalised ranking** (deferred from Stage 4 "flag-only"): exclude insufficient criteria from the weighted total + report coverage %, instead of contribution 0.
- **E3.e — regression gates**: now a baseline exists, set thresholds (e.g. grounding ≥ 0.95) + a scheduled run; wire BGE reranker on a box with HF egress for a fair retrieval number.
- **E3.f — scanned/OCR scenario**: add once the Modal OCR path is runnable.

### E4 — Buyer-ready reports 🟢 ~85% DONE
Done 2026-05-30: PDF + in-app HTML report (#176) — exec summary, ranking, mandatory pass/fail, weighted scoring, **evidence appendix with source quotes**, audit trail, approval routing; download from results page (#178); org/run access control; 15 tests. **Left:** **DOCX** output (reuse the jinja2 context → python-docx) + an explicit **override-history** section in the report. **Exit:** DOCX download; override history rendered; tests; sample artifact (the Phase 7 preview already serves as one).

### E5 — Approval workflow 🟡 PARTIAL
Exist: `approvals`, `audit_overrides`, `approval_assignments` tables; `/evaluate/{run}/override` (required justification) + `/admin/approval-assignments`; Phase 9 approver queue + value/dept-based assignment. **Left:** explicit approve/reject/request-change actions + status surfaced on results page & report; **notifications** (wire Phase 8 delivery — email/Teams on `approval_required`); audit every approval action. **Exit:** queue shows runs needing approval; correct approver assigned; approve/reject/request-change; unauthorized can't approve; notifications sent/queued; approval history in the report.

### E6 — Production operations 🟡 PARTIAL
Exist: `app/infra/circuit_breaker.py`, `app/providers/observability.py` (Prometheus/Grafana/Loki), rate limiter, health endpoint, written runbooks. **Left:** **load tests** (1/5/15/30 vendors) + **P50/P95/P99 latency + cost report**; backup/restore procedure (tested); execute the deployment runbook once; dashboards for per-agent latency/cost/token/failures/queue-depth/retrieval-miss/extraction-fail/override-rate; test circuit-breaker behaviour. **Exit:** runbook executed; metrics emitted; circuit-breaker tested; load-test report; backup/restore documented+tested.

### E7 — Enterprise integrations 🔴 OPEN (future, pre-purchase)
None built. **SSO/OIDC first** (IT/security gate). Then SharePoint/OneDrive import behind a clean provider interface; email/Teams notifications (Phase 8 seam); **signed** webhooks for `evaluation_complete`/`approval_required` (from `event_log`); audit/report export API; admin integration settings; document future Coupa/Ariba/Ivalua/Zip/DocuSign/CLM. **Exit:** SSO/OIDC design-or-impl; ≥1 doc-import (or stub behind interface); notification path; signed+documented webhooks; admin config; integration-fit doc.

### E8 — Product positioning ⚪ OPEN (marketing, after E1+E3)
Position as **evidence-grounded, audit-ready vendor evaluation for regulated procurement** — not a generic AI RFP assistant. Deliverables: buyer one-pager, technical-reviewer brief, **security/tenant-isolation brief** (needs E1 done), **benchmark/quality brief** (needs E3 done), sample decision report (Phase 7 PDF), demo script, ICPs (gov/health/finance/pharma/insurance/IT-security), pilot success criteria.

---

## 🔴 P0 — Blocks production launch

Things that prevent shipping to a paying customer.

### P0.16 — Tenant isolation: PostgreSQL RLS is currently INERT (external audit 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** RLS now enforces. (a) New dedicated `platform_app` role — `LOGIN NOSUPERUSER NOBYPASSRLS` — is the runtime app role (`app/db/session.py`, `fact_store.get_engine`); the owner/superuser `platformuser` is used only for DDL, identity/auth (`get_admin_db`), and cross-org system jobs. (b) `FORCE ROW LEVEL SECURITY` on all 22 protected tables + policies added for the two audit tables that lacked them (`audit_log`, `access_audit_log`). (c) The RLS context (`app.current_org_id`) is set on the **same** connection as the query via a pool checkout listener fed by a request/background ContextVar — the throwaway-connection middleware is gone, replaced by pure-ASGI `OrgContextMiddleware`; background pipeline runs inside `org_context()`. (d) `app.org_id` standardised to `app.current_org_id` everywhere (org_settings code + policies). Schema in `schema.sql` + Alembic `0011`; proven by `tests/test_tenant_isolation_rls.py` (10 tests, run as the real `platform_app` role); reviewer summary in `docs/dev/TENANT_ISOLATION.md`. README claim updated. Functional suite routed to the owner role via `tests/conftest.py` (follow-up: run it as the app role; the request path itself is proven as the real app role by `test_request_path_isolation_end_to_end`). Note: route-ownership guards on re_evaluate/override were already added in #188.

**Hardening round (same PR, post-review):** (a) **no committed DB password** — `platform_app` password is generated at runtime in CI and injected from `POSTGRES_APP_PASSWORD` (psql `-v app_pw` for schema.sql; `os.environ` in `0011`); (b) **index-friendly policies** — `org_id = NULLIF(current_setting(...),'')::uuid` (uuid compare, uses the `(org_id,…)` index) instead of `org_id::text =`; (c) **single source of truth** — FORCE applied dynamically to every RLS-enabled table (no hardcoded list); a test asserts none is left un-FORCEd; (d) **operational tables** `rfps`/`ingestion_jobs`/`event_log`/`invited_vendors` brought under RLS; (e) **fail-loud startup guard** (`_check_db_app_role`) refuses prod boot if the app role is superuser/BYPASSRLS or `POSTGRES_APP_PASSWORD` is unset; (f) **listener perf** — org stamped once per org-change per pooled connection, not per query; (g) **gitleaks** secret-scan CI job + `.gitleaks.toml` (allowlists documented dev/CI literals); (h) fixed the latent `gaps_report` column (P1.x).

<details><summary>Original finding (preserved)</summary>

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

</details>

---

### P1.x — `_db_get_run` selects non-existent `gaps_report` column (found during P0.16, 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** Added `gaps_report JSONB` to `evaluation_runs` (schema.sql `CREATE TABLE` + idempotent `ADD COLUMN IF NOT EXISTS`, and Alembic `0011`). The column is now consistent with the code that writes it (`evaluation_routes.py` gaps UPDATE) and reads it (`_db_get_run` SELECT / run-results route). Was latent (no test exercised the full SELECT); fixed as part of the P0.16 hardening round.

**Original problem.** `_db_get_run` did `SELECT … currency, gaps_report …` but `gaps_report` existed in neither schema.sql nor any migration → `UndefinedColumn` against a real DB → run-results/override/re-evaluate routes would 500.

---

### P0.12 — Multi-user visibility and role-based access

**Problem.** Today any user with a JWT for the same `org_id` can see any evaluation that org has run. RLS prevents cross-org leakage but not within-org. A procurement intern can see the CFO's confidential negotiations.

**Fix.** Role-based visibility model (owner / dept member / approver / CFO / auditor / admin) with Postgres RLS policies and an `access_audit_log` table.

**Effort.** 2-3 days.

---

### P0.17 — JWT signing secret + dev credentials silently fall back to known constants (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** `_check_auth_secrets()` added to `app/main.py` lifespan (after `_check_cors_origins`): in production (real `APP_API_KEY` set) it raises on boot if `JWT_SECRET_KEY`/`DEV_USER_PASSWORD` are unset or equal the default constant, or if `JWT_ALGORITHM=none`. Verified: guard trips with defaults, passes with strong secrets.


**Problem.** [app/config/loader.py:217](app/config/loader.py#L217),[331](app/config/loader.py#L331) default `jwt_secret_key` to `"change-me-in-production"`, and [:223](app/config/loader.py#L223) defaults `dev_user_password` to `"devpassword2026"` — with no fail-fast. If `JWT_SECRET_KEY` is unset in any deploy, anyone can forge a token for any `org_id`/`role` (incl. `platform_admin`) and the signature verifies → full cross-tenant + admin compromise. Compounded by `login()` ([app/api/auth_routes.py:160-189](app/api/auth_routes.py#L160-L189)) seeding/authenticating a `company_admin` dev user from those defaults.

**Fix.** Fail closed at startup when not in dev: if env is production (reuse the `app_api_key` production gate in `main.py`) and `JWT_SECRET_KEY` / `DEV_USER_PASSWORD` are unset or equal the default constant → raise on boot. Also pin `jwt.decode(algorithms=["HS256"])` literally (reject `none`/alg-confusion).

**Effort.** Half a day.

---

### P0.18 — Human-override audit record written with `str()` not `json.dumps()` + no RLS org context (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** `app/domain/override.py:save_override` now uses shared `get_engine()`, runs `SET LOCAL app.current_org_id` inside `engine.begin()`, and serialises both decision columns with `json.dumps(..., default=str)`. Verified `str()` produced invalid JSON where `json.dumps` round-trips. (The inline INSERT in `evaluation_routes.submit_override` already used `json.dumps` + CAST — unaffected.)


**Problem.** [app/domain/override.py:71-72](app/domain/override.py#L71-L72) binds `str(override.original_decision)` / `str(override.new_decision)` into `::jsonb` columns — Python repr (`{'k': 'v'}`, `None`, `True`) is invalid JSON → Postgres rejects/garbles the only legal path to change a decision (**Component Contract #7**). Same function ([:43-51](app/domain/override.py#L43-L51)) builds its own `create_engine` (leaks an engine per call) and never sets `app.current_org_id`, unlike every sibling — so once P0.16 makes RLS real, the override INSERT fails the policy.

**Fix.** Use `json.dumps(...)` for both decision columns; reuse `get_engine()` and set the org GUC like `org_settings.py`/`criteria.py`. Add a round-trip test (write override → read back parsed JSON).

**Effort.** Half a day.

---

### P0.19 — `user_criteria` keyed on email only → cross-tenant read/write (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** Root cause was the DB constraint (migration `0003` put column-level `UNIQUE` on `email`). New migration `alembic/versions/0009_user_criteria_org_unique.py` drops `user_criteria_email_key`, adds `uq_user_criteria_email_org` on `(email, org_id)`. Both `chat_routes` queries now scope by `org_id` (`get_criteria` WHERE; `save_criteria` `ON CONFLICT (email, org_id)`).


**Problem.** [app/api/chat_routes.py:167-194](app/api/chat_routes.py#L167-L194) reads `WHERE email = :email` and upserts `ON CONFLICT (email)` on `user_criteria` with **no `org_id`**, while the codebase explicitly allows the same email across orgs ([auth_routes.py:207](app/api/auth_routes.py#L207)). A user in Org B reads and overwrites the success-criteria of a same-email user in Org A. (Distinct from P0.16 — this is an app-layer query missing the tenant filter outright, the exact failure mode P0.16 warns about.)

**Fix.** Add `org_id` to the WHERE and to the conflict key (`ON CONFLICT (email, org_id)`); derive `org_id` from `current_user`. Add cross-org test.

**Effort.** 2 hours.

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

### P1.13 — `re_evaluate` + `override` skip `require_run_access` (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** `require_run_access(user, run)` added after `_db_get_run` in both `submit_override` and `re_evaluate` (`app/api/evaluation_routes.py`).


**Problem.** [app/api/evaluation_routes.py:880-909](app/api/evaluation_routes.py#L880-L909) (`re_evaluate`) and [:821-825](app/api/evaluation_routes.py#L821-L825) (`override`) org-scope via `_db_get_run(run_id, user.org_id)` but omit `require_run_access(user, run)` — which every sibling (`rerun`, `cancel`, `delete`, `results`) calls. Any same-org user (incl. a `department_user` with no Phase 9 visibility to the run) can re-trigger the paid LLM pipeline (cost/DoS) or override its decision on a run they cannot otherwise see. Concrete BOLA, narrower than the P0.16/P0.12 test-coverage items.

**Fix.** Add `require_run_access(user, run)` after the `_db_get_run` in both handlers; add a regression test.

**Effort.** 1 hour.

---

### P1.14 — `call_with_backoff` retries on bare `Exception` (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** Removed `Exception` from the `retry_if_exception_type` tuple in `app/infra/rate_limiter.py:call_with_backoff` — now retries only RateLimit/Timeout/InternalServer/APIConnection, matching `with_retry`.


**Problem.** [app/infra/rate_limiter.py:94](app/infra/rate_limiter.py#L94) includes `Exception` in the tenacity `retry_if_exception_type` tuple, so a deterministic error (ValueError, JSON/parse, 401, even `CancelledError`) is retried 5× with 2-60s backoff (~30s hang) before re-raising. `call_llm()` routes every provider through this, multiplied across per-vendor fan-out. The sibling `with_retry` ([:62](app/infra/rate_limiter.py#L62)) correctly lists only transient types.

**Fix.** Drop `Exception` from the set (keep RateLimit/Timeout/InternalServer/APIConnection); add the non-OpenAI providers' transient equivalents if needed.

**Effort.** 1 hour.

---

### P1.15 — OpenAI/Azure embedding sends the entire chunk list in one request (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** `_embed_openai`/`_embed_azure` now sub-batch via `_chunked(texts, 256)` and concatenate in order (`app/providers/embedding.py`). Verified chunking preserves order + full coverage over 600 items.


**Problem.** [app/providers/embedding.py:93](app/providers/embedding.py#L93) passes `input=[t[:8000] for t in texts]` for *all* chunks at once (`process_document` → `embed_batch(all_chunks)`). OpenAI caps a single embeddings request at 2048 items / ~300k tokens; a large RFP exceeds 2048 chunks → the whole ingestion 400s. The per-item char clip bounds neither array length nor aggregate tokens.

**Fix.** Sub-batch the request (≤256 items) and concatenate results in order.

**Effort.** Half a day.

---

### P1.16 — SSE stream accepts the JWT as a URL query parameter (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** `run_stream_alias` (`GET /{run_id}/stream`) now reads the JWT from the HttpOnly cookie only (`request.cookies[COOKIE_NAME]`); `?token=` removed. Frontend already opens it with `new EventSource(url, {withCredentials: true})` (`frontend/app/page.tsx`), so the cookie is sent automatically — no frontend change needed.


**Problem.** [app/api/evaluation_routes.py:680-694](app/api/evaluation_routes.py#L680-L694) decodes `?token=` directly. URL tokens land in access/proxy logs, browser history, and `Referer` — leaking an 8h-default bearer token from a copied report URL.

**Fix.** Issue a short-lived, single-use stream token (or use the cookie path) instead of the raw session JWT in the query string.

**Effort.** Half a day.

---

### P1.17 — Extraction Postgres-save failure is swallowed (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** On `save_extraction_output` failure, `run_extraction_agent` appends a HARD `fact_store_save_failed` critic flag and recomputes the verdict (`_verdict`) → BLOCKED, so `extraction_per_vendor` isolates the vendor into `failed_vendors` instead of evaluating against missing facts. Verified HARD flag → BLOCKED.


**Problem.** [app/agents/extraction.py:166-174](app/agents/extraction.py#L166-L174) wraps `save_extraction_output` in `try/except` that only `print()`s and still returns a non-BLOCKED verdict. The Evaluation Agent then reads facts from Postgres (**Contract #6**) and silently scores against zero facts — a DB write failure becomes a silent wrong answer that looks healthy.

**Fix.** On save failure mark the vendor failed (route through `failed_vendors` / a HARD critic flag) rather than `print` + continue.

**Effort.** Half a day.

---

### P1.18 — `PATCH /org/settings` 500s on `user.sub` (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** `app/api/org_settings_routes.py:32` now passes `updated_by=user.email` (TokenData has no `sub`). Module imports cleanly.


**Problem.** [app/api/org_settings_routes.py:32](app/api/org_settings_routes.py#L32) passes `updated_by=user.sub`, but `TokenData` ([jwt.py:34-38](app/auth/jwt.py#L34-L38)) has no `sub` field (it's `email`) → `AttributeError` → 500 on every PATCH; the `updated_by` audit field is never written. (Same file [:49](app/api/org_settings_routes.py#L49) also sets the legacy `app.org_id` GUC — folds into P0.16's naming-standardisation.)

**Fix.** `user.sub` → `user.email`.

**Effort.** 10 minutes.

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

### P2.0c — Phase 2c finish critic-as-controller ✅ DONE 2026-05-30

**Resolution.** Extraction + Evaluation now run under the shared in-branch controller `app.pipeline.critic_retry.run_with_critic_retry` (Explanation already had the graph-level 3-route critic node). `run_extraction_agent` / `run_evaluation_agent` gained a `critic_feedback` param that prepends a "PREVIOUS ATTEMPT FAILED" preamble to their prompts (mirrors Explanation); `extraction_per_vendor` / `evaluation_per_vendor` route through the controller (Extraction gained the block-guard it never had; Evaluation's single-shot HARD-block at nodes.py became retry-then-fail). The reducer gap below is fixed with a dedicated **deep** reducer `_merge_critic_metrics` (a shallow `_merge_dicts` would clobber the extraction bucket when evaluation writes the same vendor_id in a later stage). Telemetry rolls into `summary.json` (`_summarise_critic_metrics`) + the run event log. Planner / Ingestion / Retrieval / Comparator / Decision remain **validation-only by design** (no free-form generative claim to re-prompt). Tests: `tests/test_critic_controller_wiring.py` (10) + `tests/test_critic_retry.py` (5). Honest note preserved: 0/12 Extraction+Evaluation blocks in smoke runs → shipped as production-robustness, not an observed-failure fix.

Phase 2 plan promised all 9 agents under the Critic-as-controller pattern (retry-with-feedback, 3-way routing: continue / retry / block). Today only **Explanation** has the full pattern. The other 7 agents (Planner, Ingestion, Retrieval-partial, Extraction, Evaluation, Comparator, Decision) still run the critic inline and can only block. **Fix.** Promote Critic-as-controller to dedicated LangGraph nodes for Extraction + Evaluation first (highest leverage per the original Phase 2 plan); Planner / Ingestion / Comparator / Decision remain deferred as "reliable enough in smoke runs." **Effort:** 1 day for Extraction + Evaluation.

> **Code-review note (2026-05-30):** the wiring is blocked by a concrete gap — `run_with_critic_retry` ([app/pipeline/critic_retry.py:90](app/pipeline/critic_retry.py#L90),[103](app/pipeline/critic_retry.py#L103),[128](app/pipeline/critic_retry.py#L128)) returns a `critic_metrics_accum` key on every branch, but `PipelineState` ([app/pipeline/state.py](app/pipeline/state.py)) declares no `Annotated[dict, _merge_dicts]` field for it. When wired into the parallel per-vendor nodes, each vendor's telemetry has no reducer → last-writer-wins clobbers all but one vendor. Add the reducer field as the first wiring step. **(Addressed — see Resolution: a dedicated deep reducer was added, not the shallow `_merge_dicts`.)**

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

### P2.14 — Blocking sync I/O inside async retrieval (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** `run_retrieval_agent` now wraps `get_dense_embedding`, `search_hybrid`/`search_dense`, and `rerank_candidates` in `asyncio.to_thread(...)` so the synchronous embedding/Qdrant/reranker I/O no longer blocks the event loop and the per-vendor fan-out runs concurrently.


`run_retrieval_agent` is `async` but calls `search_hybrid`/`search_dense` + `embed_text` directly ([app/agents/retrieval.py:165](app/agents/retrieval.py#L165),[175](app/agents/retrieval.py#L175)) — synchronous Qdrant + embedding network calls, not offloaded (the reranker at :210 correctly uses `run_in_executor`). Under the per-vendor `asyncio.Semaphore` fan-out this blocks the event loop and serializes the "parallel" vendors. **Fix.** Wrap the sync calls in `run_in_executor` (or use async clients). **Effort:** Half a day.

### P2.15 — `cost_tracker` by-agent attribution always "pipeline" (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** Added `mark_agent(name)` to `cost_tracker` (sets the `_current_agent` ContextVar; per-task, so concurrent per-vendor agents don't clobber). Each LLM-calling agent's run_* function calls it at entry (retrieval/extraction/evaluation/comparator/decision/explanation). Planner makes no LLM calls so it's skipped. Verified `summary()["by_agent"]` now splits per agent.


`_current_agent` ContextVar is set once to `"pipeline"` and never per-agent, so `summary()["by_agent"]` collapses all spend into one bucket ([app/infra/cost_tracker.py:146](app/infra/cost_tracker.py#L146)) — the documented Phase 3 by-agent breakdown is non-functional (totals are correct). **Fix.** Set the ContextVar per agent/node (inside each node, per the ContextVar-in-task rule). **Effort:** Half a day.

### P2.16 — Langfuse client constructed per log call (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** `observability.py` now builds the Langfuse client once via a lazy module-level `_get_langfuse()` singleton (caches the client; remembers init failure to avoid retry storms). Both `_langfuse_log_run` and `_langfuse_log_flag` reuse it instead of constructing a new client (background thread + connection pool) per call.


`_langfuse_log_run`/`_langfuse_log_flag` ([app/providers/observability.py:69](app/providers/observability.py#L69),[101](app/providers/observability.py#L101)) instantiate a new `Langfuse()` (background thread + connection pool) on every agent-run/critic-flag and never close it — thread/socket leak under load, plus a synchronous `.flush()` on the async path. **Fix.** Module-level singleton client; offload flush. **Effort:** Half a day.

### P2.17 — `deadline_processor` event emission not idempotent (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** `_finalize_completed_rfps` now emits the lifecycle event only for RFPs whose flip-to-`facts_ready` UPDATE returned `rowcount > 0` in this tick. The UPDATE is conditional on `status='processing'` and Postgres row-locks it, so exactly one concurrent tick wins the flip and emits; the loser (and any later tick) sees `rowcount==0` and does not re-emit. Removed the prior `NOT EXISTS` second-pass that had the TOCTOU window.


[app/jobs/deadline_processor.py:206-238](app/jobs/deadline_processor.py#L206-L238) commits the status flip, then re-queries `facts_ready` rows lacking an event in a separate connection and emits per-row — two overlapping ticks can both pass the `NOT EXISTS` check and double-emit `rfp.facts_ready` (no unique constraint backs the dedup), contradicting the docstring's concurrency-safety claim. **Fix.** Unique index on `(rfp_id, event_type)` or emit in the same txn as the flip. **Effort:** Half a day.

### P2.18 — `decision._recommendation` trusts hardcoded label order vs config thresholds (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** `_recommendation` now iterates the configured thresholds sorted by value descending (`sorted(thresholds.items(), key=lambda kv: kv[1], reverse=True)`) and returns the first band the score meets — so a non-monotonic `recommendation_thresholds` edit in platform.yaml can't silently mislabel a score.


[app/agents/decision.py:50-55](app/agents/decision.py#L50-L55) returns the first label in a fixed code order whose threshold the score meets — correct only while config thresholds stay monotonic with that order. A legal `recommendation_thresholds` edit (config is customer-editable, **Contract #5**) silently mislabels the recommendation band. **Fix.** Sort bands by configured threshold value, not code order. **Effort.** 2 hours.

### P2.19 — `comparator` zero-fills missing vendors into per-criterion rankings (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** The per-criterion loop now iterates only `vendor_ids` present in `evaluation_outputs` (`for vid in (v for v in vendor_ids if v in evaluation_outputs)`), so a vendor that failed upstream is no longer given a fabricated 0 score and a real "weakest" rank position while being excluded from `overall_ranking`. Entirely-missing vendors are still warned about; an evaluated vendor lacking one criterion still gets a genuine 0.


[app/agents/comparator.py:148-150](app/agents/comparator.py#L148-L150) iterates all `vendor_ids` and assigns a fabricated score of 0 to vendors absent from `evaluation_outputs`, giving a failed vendor a real "weakest" `relative_position` in `criteria_comparisons` while it is (correctly) excluded from `overall_ranking` and HARD-blocked by the critic — inconsistent, misleading report data. **Fix.** Iterate only vendors present in `evaluation_outputs`. **Effort.** 2 hours.

### P2.20 — `CircuitBreaker` defined but never wired; half-open unbounded (code review 2026-05-30) ✅ DONE (hardened) 2026-05-30

**Resolution.** Guarded `last_failure_time is None` in the OPEN branch (no more TypeError on a forced/reset OPEN), and added a `_half_open_in_flight` flag so only one trial call probes recovery while HALF_OPEN (others get a clear RuntimeError). Verified the None path raises RuntimeError, not TypeError. NOTE: still not wired into `call_llm`/provider calls — that wiring remains deferred (the primitive is now safe for when it is wired).


[app/infra/circuit_breaker.py](app/infra/circuit_breaker.py) has no callers anywhere in `app/` (grep-confirmed) — a resilience primitive that protects nothing. If wired as-is, `last_failure_time` can be `None` in the OPEN branch (TypeError), and HALF_OPEN lets unlimited concurrent calls through instead of a single probe. **Fix.** Wire into `call_llm`/provider calls; guard the None; gate half-open to one trial. **Effort.** Half a day.

### P2.21 — `rate_monitor` reads in-process counters but runs as a separate Modal cron (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** Added a shared per-minute counter table `rate_limit_stats` (migration `0010`). The rate limiter upserts into it (`_record_rate_metric` / async `_arecord_rate_metric`, offloaded via `asyncio.to_thread`) on each LLM call and on `openai.RateLimitError`, gated by new setting `RATE_METRICS_ENABLED` (default False, so the hot path is untouched until an operator opts in + deploys the cron). `check_rate_limit_health` now SUMs the table over its window instead of calling the non-existent `RateLimiter.get_instance()/get_call_count()/get_error_count()`; returns a `no_data` result if the table/DB is unavailable rather than crashing. (Still unwired into deploy/modal.py — cost decision pending, same as before.)


[app/jobs/rate_monitor.py](app/jobs/rate_monitor.py) reads `RateLimiter.get_instance()` in-process; run as a separate Modal scheduled function it sees a fresh limiter with 0 traffic, so `error_pct` is always 0 and the alert can never fire (`_post_slack_alert` is also never called). **Fix.** Persist rate metrics (DB/Redis) and have the monitor read those, or run it in-process. **Effort.** Half a day.

### P2.22 — reranker ColBERT path imports removed `ragatouille`, fails open (code review 2026-05-30) ✅ DONE 2026-05-30

**Resolution.** `_get_colbert_model` now catches the `ragatouille` ImportError and raises a clear `RuntimeError` (configuration error — use bge/cohere or reinstall) instead of being swallowed into a silent no-rerank downgrade. The `rerank()` fallback now logs via the module `logging` logger (warning) instead of `print`, so a reranker failing open to vector-score order is visible to operators.


[app/providers/reranker.py:24-31](app/providers/reranker.py#L24-L31),[113-128](app/providers/reranker.py#L113-L128) import `ragatouille`, which CLAUDE.md says was removed from requirements. With `RERANKER_PROVIDER=colbert` the import raises, is swallowed by the broad `except` at [:66](app/providers/reranker.py#L66), and silently downgrades to no-reranking (only a `print`) — configured reranker fails open with no operator signal. **Fix.** Remove the colbert branch or reimplement on CrossEncoder; log via the structured logger, don't `print`. **Effort.** 2 hours.

### P2.23 — Critic-controller telemetry should emit Prometheus metrics, not only `summary.json` (Phase 2c follow-up 2026-05-30)

Phase 2c records per-vendor self-correction telemetry (`critic_metrics_accum` → `summary.json.critic` + a run event-log line). That's enough to *measure* the feature, but it is **not platform-grade observability**: there are no Prometheus counters, so an operator can't dashboard/alert on the production retry/recovery rate (the whole point of the "measure-first, instrument the real rate" framing). The stack already exists (`app/providers/observability.py` + Prometheus/Grafana/Loki). **Fix.** Emit `critic_blocks_total`, `critic_retry_success_total`, `critic_exhausted_total` (labelled by agent) from the controller; add a Grafana panel. **Effort.** Half a day. **Provenance.** Self-flagged during the Phase 2c architecture review — "is this how product companies build" — telemetry-to-a-file is the honest gap.

### P2.24 — Evaluation retry feedback is applied to ALL checks/criteria, not the failing one (Phase 2c follow-up 2026-05-30)

`run_evaluation_agent(critic_feedback=…)` threads ONE feedback string into **every** mandatory-check and criterion-scoring prompt on a retry, even though a HARD eval block usually concerns a single criterion. Re-prompting all of them is blunt (extra tokens, and unrelated criteria see irrelevant "you failed" text). Acceptable for v1 (retry rate is 0% on clean fixtures), but a refined design routes feedback to the specific failing check/criterion. **Fix.** Have the critic attribute each HARD flag to a `check_id`/`criterion_id`; inject feedback only into that item's prompt. **Effort.** 1 day. **Provenance.** Self-flagged during the Phase 2c architecture review.

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
