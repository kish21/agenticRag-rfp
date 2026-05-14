# Security & Trust Model
*Version 1.0 — 2026-05-14*

---

## Trust Boundaries

```
[ Public Internet ]
        │ HTTPS only
        ▼
[ FastAPI API Gateway ] — JWT validation at every endpoint
        │ org_id extracted from token
        ▼
[ Business Logic / Agents ] — org_id passed explicitly, never inferred
        │
        ├──► [ Qdrant ] — always filtered by {org_id, vendor_id}
        └──► [ PostgreSQL ] — RLS policy: SET LOCAL app.org_id per connection
                              audit tables: INSERT-only, no UPDATE/DELETE
```

---

## Authentication

| Mechanism | Implementation | File |
|---|---|---|
| JWT tokens | PyJWT, HS256 signing | `app/core/auth.py` |
| Token expiry | Configurable (default: 24h) | `app/config/loader.py` |
| Unauthenticated requests | 401 Unauthorized — no partial data returned | `app/api/routes.py` |
| Admin endpoints | Require `role=admin` claim in JWT | `app/api/admin_routes.py` |
| Service-to-service (Modal) | Modal internal auth — not exposed to public | `app_modal.py` |

---

## Authorisation (RBAC)

### Role Definitions

| Role | Description | Scope |
|---|---|---|
| `superadmin` | Platform operator — can manage all orgs | Cross-org (platform team only) |
| `admin` | Org admin — can manage tenants, users, settings within their org | Org-scoped |
| `ceo` | Executive view — read all departments, all regions within their org | Org-scoped, all departments/regions |
| `cfo` | Financial view — same as CEO, plus contract approval for >£500K | Org-scoped |
| `regional_director` | Sees their region only | Region-scoped |
| `department_head` | Sees their department only, can approve evaluations | Department-scoped |
| `procurement_manager` | Full pipeline access within their department | Department-scoped |
| `legal_reviewer` | Read-only on assigned evaluations | Evaluation-scoped |
| `auditor` | Read-only audit log export | Org audit log only |

### Permission Matrix

| Action | superadmin | admin | ceo/cfo | regional_dir | dept_head | procurement | legal | auditor |
|---|---|---|---|---|---|---|---|---|
| View all evaluations | ✓ | ✓ (own org) | ✓ | Region only | Dept only | Dept only | Assigned | ✗ |
| Upload vendor docs | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| Trigger evaluation | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| Override score | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| Approve evaluation | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| View CEO dashboard | ✓ | ✓ | ✓ | Partial | Partial | ✗ | ✗ | ✗ |
| Manage org settings | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Export audit log | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| Delete org data | ✓ | ✓ (own org) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

---

## Tenant Isolation — Two-Layer Defence

### Layer 1: API Layer

```python
# app/core/auth.py
org_id = decode_jwt(token)["org_id"]  # Server-side extraction
# org_id is NEVER accepted from request body, query params, or headers
```

- Every authenticated request has org_id injected from the JWT payload
- Any attempt to pass org_id as a query parameter or request body field is rejected
- The `superadmin` role is the only exception — required for platform monitoring only

### Layer 2: Database Layer

**PostgreSQL Row-Level Security:**
```sql
-- Schema: app/db/schema.sql
ALTER TABLE extracted_certifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON extracted_certifications
  USING (org_id = current_setting('app.org_id'));

-- Set per connection in fact_store.py:
conn.execute(text("SET LOCAL app.org_id = :o"), {"o": org_id})
```

**Qdrant Filter Enforcement:**
```python
# app/core/qdrant_client.py — every query includes:
filter=Filter(must=[
    FieldCondition(key="org_id", match=MatchValue(value=org_id)),
    FieldCondition(key="vendor_id", match=MatchValue(value=vendor_id)),
])
```

No unfiltered Qdrant queries exist in production code. The `query_points()` call always receives both filters.

---

## Hallucination Trust Model

The Critic Agent is the platform's trust enforcement mechanism for AI-generated content.

| Check | Mechanism | Consequence |
|---|---|---|
| Grounding quote present | Non-empty `grounding_quote` field in every fact | HARD block if missing |
| Grounding quote verbatim | `normalised_quote in normalised_source` — whitespace-normalised | HARD block if fails |
| Confidence floor | Per-agent configurable minimum (0.6 retrieval, 0.7 extraction) | Retry if below; SOFT flag after retry |
| Uncited claim in report | Every claim in Explanation report must reference a `source_chunk_id` | HARD block if uncited claim |
| Cross-tenant reference | org_id appears in a chunk from a different org | HARD block (should be impossible if storage layer is correct) |

**The platform makes a falsifiable commitment:** Every fact on which a decision is based can be traced to a specific page of a specific vendor document. If a fact cannot be grounded, the pipeline stops.

---

## Audit Integrity

### Immutable Audit Trail

```sql
-- audit_overrides: INSERT-only by design
-- No UPDATE trigger:
CREATE RULE no_update_audit AS ON UPDATE TO audit_overrides DO INSTEAD NOTHING;
CREATE RULE no_delete_audit AS ON DELETE TO audit_overrides DO INSTEAD NOTHING;
```

### Override Policy

1. Human clicks "Override" in the UI
2. Justification field is mandatory — system rejects empty string (422)
3. `app/core/override_mechanism.py` creates an `AuditOverride` row
4. Row includes: `user_id`, `org_id`, `run_id`, `field_overridden`, `original_value`, `new_value`, `justification`, `timestamp`
5. Row is immutable — no direct database edit is possible

### 7-Year Retention

Enforced via the cleanup job (`app/jobs/cleanup.py`):
- Runs daily (Modal scheduled function)
- Deletes `evaluation_runs` older than the retention period
- **Never** deletes from `audit_overrides`, `org_settings_audit` — these are permanent

---

## Secrets Management

| Secret | Storage | Notes |
|---|---|---|
| LLM API keys | `.env` environment variable | Never in YAML or source code |
| Database credentials | `.env` environment variable | |
| JWT signing key | `.env: JWT_SECRET_KEY` | Rotate without service restart |
| Modal credentials | `modal secret` (Modal platform) | Not in `.env` |
| LangFuse keys | `.env` | |

**What is never committed to source control:**
- `.env` (gitignored)
- Any file containing `API_KEY`, `SECRET`, `PASSWORD`, `TOKEN` literals
- Database dumps

---

## Known Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM prompt injection via vendor PDF | Medium | High | Critic agent hard-blocks on suspicious extractions; grounding check limits injection blast radius |
| Cross-tenant data leak | Low | Critical | Two-layer isolation (JWT + RLS + Qdrant filter); automated isolation tests |
| JWT secret rotation causing auth outage | Low | High | JWT secret rotation procedure in deployment runbook; rolling restart |
| Modal cold start causing LLM timeout | Medium | Medium | 10-minute timeout configured; exponential backoff; rate limiter handles retries |
| Audit table data loss | Very Low | Critical | Insert-only design; PostgreSQL daily backups; 30-day retention |
| Vendor submits malicious PDF (malware) | Low | Medium | File type validation; no execution of PDF content; OCR only via Modal sandbox |
