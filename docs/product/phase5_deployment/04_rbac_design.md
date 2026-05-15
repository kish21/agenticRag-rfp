# RBAC Design — Role-Based Access Control
*Version 1.0 — 2026-05-14*

---

## Role Hierarchy

```
superadmin (platform team only)
  └── admin (per-org admin)
        ├── ceo / cfo (org-wide read, approval authority)
        ├── regional_director (region-scoped)
        │     └── department_head (dept-scoped, approval authority)
        │           └── procurement_manager (full pipeline, dept-scoped)
        │                 └── legal_reviewer (read-only, evaluation-scoped)
        └── auditor (audit log read-only)
```

---

## JWT Claims Structure

```json
{
  "sub": "user-uuid",
  "org_id": "acme-corp",
  "role": "procurement_manager",
  "department_id": "it-dept",
  "region_id": "uk-south",
  "exp": 1748000000
}
```

All scoping (`org_id`, `department_id`, `region_id`) is extracted from the JWT server-side. It is never accepted from request body or query parameters.

---

## Role Definitions

### superadmin
- **Scope:** Entire platform (all orgs)
- **Who:** Platform engineering team only — never given to customers
- **Can:** Create/delete orgs, view any org's data, rotate master JWT key
- **Cannot:** Override audit records

### admin
- **Scope:** Their org_id only
- **Who:** IT Admin at the customer organisation
- **Can:** Create/deactivate users, configure org settings, onboard departments, rotate org API keys, export audit log, delete org data (GDPR)
- **Cannot:** See other orgs' data

### ceo / cfo
- **Scope:** All departments + all regions within their org
- **Who:** C-suite executives
- **Can:** View CEO dashboard (all metrics), drill into any evaluation, approve contracts (CFO: >$500K), download PDF reports
- **Cannot:** Trigger evaluations, apply score overrides, manage users

### regional_director
- **Scope:** Their region_id only
- **Who:** Regional Managing Directors, Regional CFOs
- **Can:** View all evaluations in their region, approve contracts $100K–$500K, view regional spend dashboard
- **Cannot:** See other regions' data

### department_head
- **Scope:** Their department_id only
- **Who:** Director of IT, Director of HR, etc.
- **Can:** View their department's evaluations, approve contracts <$100K, view department spend
- **Cannot:** See other departments' data, trigger evaluations, apply score overrides

### procurement_manager
- **Scope:** Their department_id (same region)
- **Who:** Procurement analysts, senior procurement managers
- **Can:** Upload vendor documents, trigger evaluations, view extraction results, apply overrides (with mandatory justification), generate PDF reports
- **Cannot:** Approve contracts (approval is a separate role), see other departments

### legal_reviewer
- **Scope:** Evaluations explicitly shared with them
- **Who:** In-house legal team, external solicitors
- **Can:** Read evaluation reports, view extracted contract clauses, add review comments
- **Cannot:** Change scores, approve evaluations, see evaluations not shared with them

### auditor
- **Scope:** Audit log for their org
- **Who:** External auditors, internal compliance team
- **Can:** Export audit log (all decisions, all overrides, all critic flags) for their org
- **Cannot:** See evaluation content, vendor documents, or scores

---

## API Endpoint Access Matrix

| Endpoint | super | admin | ceo/cfo | reg_dir | dept_head | procurement | legal | auditor |
|---|---|---|---|---|---|---|---|---|
| `POST /evaluations` (trigger) | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| `GET /evaluations` (list) | ✓ | ✓ | All | Region | Dept | Dept | Assigned | ✗ |
| `GET /evaluations/{id}` (detail) | ✓ | ✓ | ✓ | Region | Dept | Dept | Assigned | ✗ |
| `POST /evaluations/{id}/override` | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| `POST /evaluations/{id}/approve` | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| `GET /dashboard/ceo` | ✓ | ✓ | ✓ | Partial | Partial | ✗ | ✗ | ✗ |
| `POST /upload` | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| `GET /audit/export` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `GET /admin/orgs` | ✓ | Own org | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `POST /admin/orgs` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `PUT /admin/orgs/{id}/settings` | ✓ | Own org | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `DELETE /admin/orgs/{id}/data` | ✓ | Own org | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

---

## Data Scoping Rules (Enforced Server-Side)

| Role | `evaluation_runs` filter | `extracted_*` filter | Dashboard filter |
|---|---|---|---|
| superadmin | None (all orgs) | None | None |
| admin | `org_id = JWT.org_id` | Same | Same |
| ceo/cfo | `org_id = JWT.org_id` | Same | Same |
| regional_director | `org_id = JWT.org_id AND region_id = JWT.region_id` | Same | Same |
| department_head | `org_id = JWT.org_id AND department_id = JWT.department_id` | Same | Same |
| procurement_manager | Same as department_head | Same | Same |
| legal_reviewer | `evaluation_id IN shared_evaluations(user_id)` | Same | None |
| auditor | N/A (audit log only) | N/A | None |

---

## Approval Tier vs. RBAC

The approval tier (contract value routing) is separate from RBAC role:

| Contract Value | Required Approver Role | Configured In |
|---|---|---|
| < $100K | `department_head` | `org_settings.approval_tier_1_threshold` |
| $100K – $500K | `regional_director` | `org_settings.approval_tier_2_threshold` |
| $500K – $1M | `cfo` | `org_settings.approval_tier_3_threshold` |
| > $1M | `board` | `org_settings.approval_tier_4_threshold` |

These thresholds are configurable per org via admin API. They are not hardcoded.

---

## User Management

### Create User
```bash
curl -X POST https://<api>/admin/users \
  -H "Authorization: Bearer <admin-token>" \
  -d '{
    "email": "james.okafor@acme.com",
    "role": "procurement_manager",
    "department_id": "it-dept",
    "region_id": "uk-south"
  }'
```

### Deactivate User
```bash
curl -X PUT https://<api>/admin/users/{user_id} \
  -H "Authorization: Bearer <admin-token>" \
  -d '{"active": false}'
```

Deactivated users' JWTs are rejected immediately (user lookup happens on each request).

### Role Change
Role changes require creating a new JWT. Existing tokens with old role remain valid until expiry (max 24h). For immediate role revocation: deactivate user, recreate with new role.
