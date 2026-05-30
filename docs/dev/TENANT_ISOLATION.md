# Tenant Isolation — Reviewer Summary

*Audience: a security-conscious buyer or due-diligence reviewer.*
*Status: implemented and tested (P0.16, 2026-05-30).*

## Model

Every tenant is an `org_id` (UUID). `org_id` is taken **only** from a
cryptographically verified JWT — never from a request body, query string, or
client-controlled header. Isolation is defended at three independent layers:

1. **JWT** — `OrgContextMiddleware` decodes the token (cookie or Bearer) and
   binds the caller's `org_id` to a request-scoped ContextVar.
2. **Application filters** — every run/RFP/vendor lookup is scoped
   `WHERE org_id = :caller_org` (e.g. `_db_get_run`), plus role/run/vendor
   ownership checks (`require_run_access`, Phase 9 visibility).
3. **PostgreSQL Row-Level Security** — the database itself rejects cross-org
   rows, so a single forgotten `WHERE` clause cannot leak data.

## How RLS is actually enforced

RLS is only meaningful if the connecting role is one the database constrains.
Two facts make that true here:

- **The app connects as `platform_app`** — a dedicated `LOGIN` role that is
  `NOSUPERUSER` and `NOBYPASSRLS`. (A superuser or `BYPASSRLS` role would ignore
  every policy — the bug this work fixed.) The owner/superuser role
  (`platformuser`) is used **only** for DDL/migrations, identity/auth lookups,
  and cross-org system jobs (cron, startup sweeps). See `app/db/session.py`.
- **`FORCE ROW LEVEL SECURITY`** is set on all 22 protected tables, so the
  policy applies even to the table owner — defense in depth if anything ever
  connects as the owner.

Each policy is `USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)`
— compared as **uuid, not text**, so the org filter uses the `(org_id, …)`
btree index instead of a sequential scan (matters at multi-tenant scale; RLS
adds negligible overhead to an evaluation run). `org_settings` keeps a text
comparison (its `org_id` is text); the three access-control tables
(`user_departments`, `rfp_collaborators`, `approval_assignments`) use a join to
the owning row.

The GUC is set on the **same connection** that runs the query: a SQLAlchemy
pool `checkout` listener stamps `app.current_org_id` from the request/background
ContextVar. It remembers the last value per pooled connection and only re-issues
the `set_config` when the org changes (one round-trip per org-change, not per
query). A connection returned to the pool is always re-stamped on its next
checkout, so it can never serve another tenant with a stale context. Background
pipeline work runs inside `org_context(org_id)`; per-row writers (fact store,
audit) also set it locally. A startup check (`_check_db_app_role`) refuses to
boot in production if the app connects as a superuser/BYPASSRLS role or
`POSTGRES_APP_PASSWORD` is unset.

## What happens on cross-org access

- **Reads** of another org's rows return **zero rows** (route → 404).
- **Missing context** (no/invalid token) → `current_setting` is empty → policy
  matches nothing → **zero rows** (fails closed, not open).
- **Writes** stamped with another org are rejected by the policy's `WITH CHECK`
  (`new row violates row-level security policy`); cross-org `UPDATE`/`DELETE`
  affect zero rows.

## What proves it

`tests/test_tenant_isolation_rls.py` runs as the real `platform_app` role and
asserts: role is non-privileged; `FORCE` on all 22 tables; no legacy `app.org_id`
GUC remains; the two audit tables now have policies; read/write isolation across
two orgs; zero rows with no context; and the application-layer org-scoping
predicate. The functional suite runs as the owner (see `tests/conftest.py`) so
it exercises business logic, not DB plumbing.

## Coverage

Under RLS: the 22 evaluation/fact/decision/audit tables **plus** the operational
tenant tables `rfps`, `ingestion_jobs`, `event_log`, and `invited_vendors`
(isolated via a join to its RFP, since it has no `org_id`). `FORCE` is applied
dynamically to every RLS-enabled table, so a newly-protected table is covered
automatically (a test asserts no RLS table is left un-FORCEd).

Credentials: the `platform_app` password is **never** in source — it is
generated at runtime in CI and injected from `POSTGRES_APP_PASSWORD` (via
`psql -v app_pw=…` for `schema.sql`, and `os.environ` in migration `0011`). A
gitleaks CI job scans for any hardcoded secret.

## Known limitations / follow-ups

- `organisations` and the billing/module shell tables are not org-RLS'd (the
  identity/billing layer; `organisations.org_id` is the tenant's own PK). They
  are reached via the admin/auth path or app-filtered.
- The functional test suite runs as the owner role (see `tests/conftest.py`) so
  it tests business logic; the request path is proven as the real `platform_app`
  role by `test_request_path_isolation_end_to_end`. Migrating the whole suite to
  the app role is a tracked follow-up.
