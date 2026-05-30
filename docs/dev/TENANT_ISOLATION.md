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

Each policy is `USING (org_id::text = current_setting('app.current_org_id', true))`.
The GUC is set on the **same connection** that runs the query: a SQLAlchemy
pool `checkout` listener stamps `app.current_org_id` from the request/background
ContextVar (and resets it on check-in, so a pooled connection never carries one
tenant's context into another's request). Background pipeline work runs inside
`org_context(org_id)`; per-row writers (fact store, audit) also set it locally.

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

## Known limitations / follow-ups

- A small set of operational tables (`rfps`, `ingestion_jobs`, `invited_vendors`,
  `event_log`, `organisations`, billing/module shells) are **not** under RLS;
  they are protected by application-layer org filters only. Adding RLS to them
  is tracked as a follow-up.
- The functional test suite runs as the owner role; migrating it to run as
  `platform_app` under per-test `org_context` (full end-to-end RLS coverage) is
  a tracked follow-up.
- The `platform_app` password ships with a dev/CI default in `schema.sql`;
  **production must rotate it** (`ALTER ROLE platform_app PASSWORD …`) and set
  `POSTGRES_APP_PASSWORD` to match.
