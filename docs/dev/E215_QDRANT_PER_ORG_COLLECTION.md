# E215 — Qdrant: one collection per org (was one per vendor)

*Issue #215 · ADR-001 revisit · 2026-06-04*

## Problem

Qdrant collections were keyed per `(org_id, vendor_id)` — one collection per
vendor proposal. At the documented 100-customer scale that is
100 × 10 RFPs × 3 vendors ≈ **3,000 collections**, each 100–300 chunks. Qdrant
pre-allocates HNSW index structures per collection, so thousands of tiny
collections carry non-trivial aggregate memory overhead even at low document
counts. This is a scaling wall, and migrating later (with live data) is harder
than changing the naming before data accumulates.

## Decision

Move to **one collection per org**: `{prefix}_{org_id}`. Vendor scoping relies
on the `org_id` **and** `vendor_id` payload filters that **already** run on
every query (`search_dense`, `search_hybrid`). The per-vendor collection
boundary was redundant with those filters — this change removes the redundant
boundary, not an isolation layer.

### Isolation posture (signed off by user, 2026-06-04)

| Boundary | Before | After |
|---|---|---|
| **Cross-org** (the real tenant boundary, the security-critical one) | physical (separate collection) | **physical (separate collection) — UNCHANGED** |
| Within-org, cross-vendor | physical (separate collection) | payload filter (`org_id` + `vendor_id`), already enforced on every query |

Cross-tenant isolation is unchanged. Only within-tenant vendor separation moves
from a physical collection boundary to the existing label-filter. `/security-review`
run on this change to prove no cross-vendor leakage inside a shared collection.

### Existing data (signed off by user, 2026-06-04)

Existing per-vendor collections hold **disposable test data** → **clear and
re-ingest**. No automated point-migration script is built; defer that until a
real production org needs zero-downtime migration.

## Interaction map (typed boundaries)

```
ingestion.py  → org_collection_name(org_id) → create_collection (idempotent) → upsert_chunk(payload has org_id+vendor_id)
retrieval.py  → org_collection_name(org_id) → search_hybrid/search_dense(collection, org_id, vendor_id, ...)  [filters unchanged]
cleanup.py    → delete points WHERE org_id=X (FilterSelector) → drop collection if now empty
qdrant.py     → delete_vendor_data(org_id, vendor_id) = GDPR single-vendor delete by filter (no longer drops a whole collection)
```

`search_dense` / `search_hybrid` signatures and bodies are **unchanged** — they
already take `collection` + `org_id` + `vendor_id` and filter on both. Only the
*collection name* passed in changes (per-org instead of per-vendor).

## Changes

| File | Change |
|---|---|
| `app/retrieval/qdrant.py` | `collection_name(org_id, vendor_id)` → **`org_collection_name(org_id)`**. `delete_vendor_collection` → **`delete_vendor_data(org_id, vendor_id)`** (delete points by filter, not the collection). |
| `app/agents/ingestion.py` | call `org_collection_name(org_id)` |
| `app/agents/retrieval.py` | call `org_collection_name(org_id)` |
| `app/jobs/cleanup.py` | delete points by `org_id` filter from the per-org collection, then drop the (now-empty) collection — instead of deleting collections by prefix |
| `tools/contract_tests.py` | rewrite `c_qdrant_naming`: different orgs → different collections; same org/different vendors → **same** collection (vendor isolation is the filter, covered by `c_qdrant_search_filters`) |
| `tools/checkpoint_runner.py` | import `org_collection_name` (only used to smoke the Qdrant connection) |
| `docs/.../ADR-001` | mark **superseded-pending** for the naming convention |
| `docs/.../03_capacity_planning.md` | update the collection-count maths |

Out of scope: `rfp_collection_name` (RFP-doc collections are 1/RFP, not the 30×
vendor multiplier, and the symbol is currently unused in product code).

## Exit criteria (testable)

1. `org_collection_name("org-a")` == `org_collection_name("org-a")` for any vendor;
   `org_collection_name("org-a")` != `org_collection_name("org-b")`.
2. Ingesting two vendors of one org writes both into **one** collection; a
   retrieval for vendor A in that collection returns **zero** chunks belonging to
   vendor B (filter isolation holds inside a shared collection). ← the security-critical test
3. `delete_vendor_data(org, vendorA)` removes only vendor A's points; vendor B's
   points in the same collection survive.
4. `run_cleanup` deletes the expired org's points and drops the empty collection.
5. Contract tests 14/14 (rewritten naming contract passes); full pytest green;
   `drift_detector` OK.
6. `/code-review` + `/security-review` clean (or findings triaged).

## Test plan

- **Unit** (`tests/test_qdrant_per_org_collection.py`, in-memory `QdrantClient`):
  per-org naming; two vendors → one collection; vendor-A query excludes vendor-B
  (the leak test); `delete_vendor_data` deletes only the target vendor.
- **Contract** (`tools/contract_tests.py`): rewritten `c_qdrant_naming` +
  unchanged `c_qdrant_search_filters` (org_id+vendor_id still required).
- **Regression**: full pytest suite (no caller left on the old two-arg name).
