# P2.27 — per-setup retention precision (was org-coarse delete)

**Status:** DONE · **Scope:** cleanup-job correctness (data deletion) · **Date:** 2026-06-05 · **Provenance:** surfaced by #215 (E215)

## The bug

The daily cleanup job (`app/jobs/cleanup.py`) deleted Qdrant data at **org
granularity**: for each expired `evaluation_setups` row it called
`delete_org_data(org_id)`, which removes **every** point owned by that org and
drops the per-org collection (E215). A Qdrant point carried `org_id` / `vendor_id`
/ `rfp_id` / `doc_id` but **no `setup_id`**, so a single expired setup wiped the
org's *other, still-live* setups too.

This was **pre-existing** (the pre-E215 code did the same via a
`startswith("platform_{org_id}_")` prefix delete) and was faithfully preserved by
#215 — not introduced by it. It is the one #215 piece that was **not live-tested**,
because exercising it deletes data.

## The fix

Stamp `setup_id` on each chunk payload at ingestion, then delete by `setup_id`.

| File | Change |
|---|---|
| `app/agents/ingestion.py` | add `"setup_id": evaluation_setup.setup_id` to the chunk payload (the `EvaluationSetup` was already in scope — no signature change) |
| `app/retrieval/qdrant.py` | new `delete_setup_data(org_id, setup_id) -> (matched, dropped)`: delete points matching `org_id`+`setup_id`, drop the collection only if it is now empty |
| `app/jobs/cleanup.py` | call `delete_setup_data` per expired setup (was `delete_org_data` once per org); summary gains `purged_setups` / `deleted_points` |

`delete_org_data` is kept as the whole-tenant GDPR-erasure primitive (parallel to
`delete_vendor_data`); its docstring is corrected to note the cleanup job no
longer uses it.

### The correctness link (verified)

The `setup_id` stamped at ingestion is the **same** id the cleanup job deletes
by: `EvaluationSetup.setup_id` (passed into `run_ingestion_agent`) is persisted as
the `evaluation_setups.setup_id` primary key (`fact_store.py` `INSERT ...
evaluation_setups (setup_id, ...)` from `setup_dict["setup_id"]`), and cleanup
reads `SELECT setup_id, org_id FROM evaluation_setups`. So an expired setup's
`setup_id` matches exactly the points stamped for it.

### Tenant isolation

`delete_setup_data` filters on `org_id` **and** `setup_id`. Cross-org is already a
physical collection boundary (E215, unchanged); the extra `org_id` predicate keeps
the tenant boundary explicit (defence in depth) even though `setup_id` is a uuid.

## Backward compatibility

Points ingested **before** P2.27 carry no `setup_id`, so `delete_setup_data` does
not match them — they are pre-fix **disposable test data**, bounded by the 90-day
retention. No prod data exists yet (#215). A clean deployment (all data ingested
post-fix) stamps every point, so when an org's last setup expires the collection
empties and is dropped correctly. We deliberately did **not** add an org-coarse
fallback — that would re-introduce the exact bug (wiping live setups).

## Self-review fixes (`/code-review` medium, 2 parallel agents)

Two findings applied (one correctness-adjacent, one cleanup):
- **Robustness (cleanup ordering):** previously a Qdrant delete failure was
  swallowed (`except Exception: pass`) but the PostgreSQL row was *still* deleted
  and committed — orphaning that setup's vectors forever (no retry, since the
  tracking row was gone). Now a vector-delete failure **keeps the PG row**
  (`continue`) so a future run retries it, and is counted as `failed_setups` in
  the summary for observability. (Pre-existing behaviour on lines P2.27 touched.)
- **DRY:** `delete_setup_data` and `delete_org_data` were near-identical
  (count → delete-by-filter → drop-if-empty), differing only in the filter.
  Extracted `_delete_by_filter_and_maybe_drop(org_id, must)`; both call it (the
  same single-sourcing `_tenant_must` does for the read path).

Findings deliberately NOT actioned: the pre-P2.27-orphan case (documented above —
bounded, no prod data, an org-coarse fallback would re-introduce the bug); and
the per-setup re-check cost (negligible for a tiny-N daily job, now consolidated
in the shared helper).

## Tests (offline, never touch real data)

`tests/test_cleanup_setup_precision.py` (7):
- `delete_setup_data` removes only the target setup; co-tenant setup + collection survive (in-memory Qdrant);
- drops the collection when the org's **last** setup is deleted;
- missing collection → `(0, False)`;
- a non-matching `setup_id` (e.g. pre-P2.27 points) removes 0 and does not drop a non-empty collection;
- ingestion stamps `setup_id` on the real payload-build path (capture `upsert_chunk`);
- `run_cleanup` calls the precise per-setup delete for each expired setup and removes only the expired PostgreSQL rows (in-memory SQLite engine);
- `run_cleanup` KEEPS the PG row when the vector delete raises (retry next run, `failed_setups` counted).

## Verification

- New tests: 7 passed. Full suite **312 passed, 3 skipped**; contracts 14/14; drift OK.
- Tenant isolation: `delete_setup_data` filters on `org_id`+`setup_id`; cross-org is the unchanged physical collection boundary (E215) — no cross-tenant deletion surface.

## Follow-up

A future GDPR/retention admin endpoint can wire `delete_org_data` (whole tenant)
and `delete_vendor_data` (one vendor) — both are tested erasure primitives with no
caller yet, consistent with the data-deletion API family built in #215.
