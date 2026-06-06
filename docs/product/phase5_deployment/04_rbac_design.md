# RBAC Design — Role-Based Access Control
*Version 2.0 — 2026-06-06 (reconciled to the as-built implementation; #55)*

> **Note:** v1.0 of this doc described an aspirational 8-role hierarchy
> (superadmin / regional_director / department_head / procurement_manager /
> legal_reviewer …) that was **never built**. This version documents what the
> code actually enforces. The original vision is preserved in git history.

---

## Role Hierarchy (as built)

Five JWT roles, validated in `app/auth/jwt.py :: VALID_ROLES` and constrained in
`users.role` (`app/db/schema.sql`, CHECK incl. `auditor` via migration 0015):

```
platform_admin    — operator/platform team; cross-org; no customer data
company_admin     — org-wide admin within one org
department_admin  — manages criteria templates + approvals; org-wide run visibility
department_user   — runs evaluations; can override with documented reason
auditor           — READ-ONLY compliance; sees the org audit trail, NOT run content
```

Two finer-grained dimensions sit *alongside* (not inside) the JWT role:
- **Ownership / collaboration / approval** — `created_by_email`, `user_departments`,
  `rfp_collaborators`, `approval_assignments` (the "owner / dept-member / approver"
  concepts from issue #55). These drive per-run visibility, not the JWT role.
- **Approver label** — `approval_assignments.approver_role` is a free-text label
  (`cfo` / `cto` / `legal` / …) used for approval routing; it is **not** a JWT role.

---

## JWT Claims Structure

```json
{
  "sub": "user@org.com",
  "org_id": "<uuid>",
  "role": "department_user",
  "dept_id": "it-dept",
  "jti": "<uuid>",
  "exp": 1748000000
}
```

`org_id` / `role` / `dept_id` are extracted server-side from the signed JWT — never
accepted from request body or query parameters. `jti` keys the `auth_sessions`
allowlist for server-side revocation (E2 auth hardening).

---

## Authorisation model — two enforcement layers

### 1. Tenant isolation (Postgres RLS) — the hard boundary
Every org-scoped table has `ROW LEVEL SECURITY` **enabled and FORCED** (migration
0011). The app connects as the non-superuser role `platform_app`
(`NOBYPASSRLS`); `OrgContextMiddleware` stamps `app.current_org_id` on the
connection, and each RLS policy is `org_id = current_setting('app.current_org_id')`.
Result: **cross-org data leakage is physically impossible**, independent of any
application bug.

### 2. Within-org visibility (default-deny) — `runs_visible_to()`
A user may see a run **iff** any predicate holds (else: nothing, same org or not):
1. wide role — `platform_admin` or `company_admin`,
2. they created it (`created_by_email`),
3. they belong to the run's department (`user_departments`),
4. they were explicitly invited (`rfp_collaborators`),
5. they are an assigned approver (`approval_assignments`).

Canonical SQL: `runs_visible_to()` in `schema.sql`; Python wrapper:
`app/domain/visibility.py`. Per-run endpoints enforce it via
`app/auth/rbac.py :: require_run_access` (403 otherwise). `department_admin` is
treated as wide for visibility in the Python wrapper (`rbac.py :: _WIDE_ROLES`).

---

## API Endpoint Access Matrix (as built)

| Endpoint | platform_admin | company_admin | department_admin | department_user | auditor |
|---|---|---|---|---|---|
| `POST /evaluate/start` | ✓ | ✓ | ✓ | ✓ | ✗ (403) |
| `GET /evaluate/list` | all org | all org | all org | own | ∅ (empty) |
| `GET /evaluate/{id}/*` (setup/results/decision/cost/audit/export) | ✓ | ✓ | ✓ | if visible | ✗ (403) |
| `POST /evaluate/{id}/override` | ✓ | ✓ | ✓ | ✗ (403)¹ | ✗ (403) |
| `POST /evaluate/{id}/{confirm,re-evaluate,cancel}`, `DELETE` | ✓ | ✓ | ✓ | if visible | ✗ (403) |
| `GET /api/v1/audit/access-log` | ✓ | ✓ | ✗² | ✗² | ✓ |
| `GET /api/v1/audit/events` | ✓ | ✓ | ✗² | ✗² | ✓ |
| `POST /api/v1/rfps`, admin attribution writes | ✓ | ✓ | ✓ | ✓ | ✗ (write_roles) |
| `DELETE /admin/org/{id}/data` (GDPR) | ✓ | own org | ✗ | ✗ | ✗ |

¹ override requires `department_admin` or above (`rbac.py :: require_admin_role`).
² audit-read roles are **config-driven** — `product.yaml rbac.audit_read_roles`
  (default `[auditor, company_admin, platform_admin]`). Widen/narrow without a code change.

---

## The `auditor` role (#55)

- **Who:** external auditors / internal compliance.
- **Can:** read the org-wide audit trail — `access_audit_log` (who viewed which run,
  when) and `audit_log` (overrides, state-change events) — via `GET /api/v1/audit/*`.
- **Cannot:** start/confirm/override/cancel/delete runs; see run setup, results,
  decisions, costs, or vendor content (`/list` returns empty; every per-run endpoint
  403s via default-deny). Not in `write_roles`, so all write surfaces 403.
- **Enforcement:** `app/auth/rbac.py :: require_audit_read` (config-driven).

---

## Approval Tier vs. RBAC

Approval routing (by contract value) is separate from the JWT role and configured
per org in `org_settings` (thresholds are not hardcoded). The required approver is
recorded as `approval_assignments.approver_role` (free-text: `cfo` / `cto` / …) and
the assignee is a real user; being an assignee grants visibility of that run only.

---

## Audit & revocation

- Every sensitive read is logged fire-and-forget by `rbac.py :: log_access`
  → `access_audit_log`. State changes are logged by `app.infra.audit` → `audit_log`.
- Deactivated users / revoked tokens are rejected per-request via the
  `auth_sessions` allowlist (E2). Role change → mint a new JWT; old tokens remain
  valid until expiry unless the session is revoked.
