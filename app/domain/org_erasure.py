"""
GDPR Mode B — whole-tenant erasure (issue #119, SC-001).

`erase_org()` is the single, deliberate, audited operation that wipes everything
the platform directly controls for ONE departing customer:

    PostgreSQL rows  →  Qdrant vectors  →  on-disk uploaded files  →  in-memory
    caches,  then writes a retained, anonymized erasure RECEIPT as proof.

GDPR framing (decided with the owner — see docs/dev/119.md): the "right to be
forgotten" is about a *person's* personal data. A company leaving and asking us
to delete their tenant is offboarding, not an Art. 17 subject request. This is
Mode B. Mode A (anonymize one individual, keep the business/audit records) is a
separate, documented follow-up.

Layering: this is a domain orchestrator. It calls the Qdrant adapter
(app/retrieval/qdrant.py), the fact-store purge (app/db/fact_store.py) and reads
config — it does NOT import the API layer. The drops_root path comes from config,
not from app/api/rfp_routes.py, to keep the dependency pointing inward.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from pydantic import BaseModel, Field

from app.config import settings
from app.db.fact_store import get_admin_engine, purge_org_postgres
from app.domain.org_settings import invalidate_org_settings
from app.infra.cost_tracker import clear_run_cost
from app.retrieval.qdrant import delete_org_data

log = logging.getLogger(__name__)


class ErasureReceipt(BaseModel):
    """Retained, anonymized proof that a tenant was erased (no PII).

    Persisted as the `detail` of an `org.erased` audit_log row, which survives
    the org delete because audit_log has no FK to organisations.
    """
    org_id: str
    requested_by: str
    reason: str
    erased_at: str                              # ISO-8601 UTC
    postgres_deleted: dict[str, int]            # table → rowcount
    qdrant_points_deleted: int
    qdrant_collection_dropped: bool
    drop_folders_deleted: int
    receipt_persisted: bool = False             # was the org.erased row written
    residual_gaps: list[str] = Field(default_factory=list)


# Honest record of what a tenant wipe does NOT reach today (see docs/dev/119.md).
_RESIDUAL_GAPS = [
    "llm_response_cache is tenant-blind (no org_id) — cannot be selectively erased",
    "LangSmith traces are external — deletion is a best-effort follow-up",
]


def _ids_to_clean(org_id: str) -> tuple[list[str], list[str]]:
    """(rfp_ids, run_ids) for the org, read BEFORE the purge deletes those rows.

    rfp_ids drive on-disk drop-folder removal; run_ids drive in-memory cost-state
    cleanup. One admin connection serves both reads.
    """
    engine = get_admin_engine()
    with engine.connect() as conn:
        rfp_ids = [r[0] for r in conn.execute(
            sa.text("SELECT rfp_id FROM rfps WHERE org_id = CAST(:oid AS uuid)"),
            {"oid": str(org_id)},
        ).fetchall()]
        run_ids = [r[0] for r in conn.execute(
            sa.text("SELECT run_id::text FROM evaluation_runs WHERE org_id = CAST(:oid AS uuid)"),
            {"oid": str(org_id)},
        ).fetchall()]
    return rfp_ids, run_ids


def _delete_drop_folders(rfp_ids: list[str]) -> int:
    """Remove {drops_root}/{rfp_id} for each of the org's RFPs. Returns count removed.

    Defence in depth for a destructive (rmtree) path: although rfp_id is read
    from the DB and constrained to a safe charset at write time, we still resolve
    and assert each target stays strictly under drops_root before deleting, so a
    crafted/legacy id (e.g. one containing '..') can never escape the root.
    """
    drops_root = Path(settings.platform.ingestion.drops_root).resolve()
    removed = 0
    for rfp_id in rfp_ids:
        target = (drops_root / rfp_id).resolve()
        if target == drops_root or drops_root not in target.parents:
            log.warning("skipping drop-folder outside root: rfp_id=%r", rfp_id)
            continue
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            removed += 1
    return removed


def _write_receipt(receipt: ErasureReceipt) -> bool:
    """Insert the retained org.erased audit row. Uses the admin engine (the org
    row, and its RLS context, are gone). Unlike app.infra.audit.audit() this does
    NOT swallow errors — a compliance receipt must be known to have persisted."""
    engine = get_admin_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO audit_log (org_id, run_id, event_type, actor, detail)
                VALUES (CAST(:org_id AS uuid), NULL, 'org.erased', :actor,
                        CAST(:detail AS jsonb))
                """
            ),
            {
                "org_id": receipt.org_id,
                "actor": receipt.requested_by,
                "detail": json.dumps(receipt.model_dump()),
            },
        )
    return True


def erase_org(org_id: str, *, requested_by: str, reason: str) -> ErasureReceipt:
    """Erase one tenant in full and return the retained erasure receipt.

    Order (each step independent of the next's success on the same store):
      1. Qdrant vectors        — delete_org_data()
      2. PostgreSQL rows       — purge_org_postgres() (one FK-safe transaction)
      3. On-disk drop folders  — rmtree per RFP
      4. In-memory caches      — org_settings cache + per-run cost accumulators
      5. Retained receipt      — org.erased audit row (config-gated)

    The receipt is written LAST, only after the destructive steps succeed, so a
    failed/rolled-back purge never produces a false "erased" proof.
    """
    # Capture ids that the purge is about to delete (disk + cache cleanup need them).
    rfp_ids, run_ids = _ids_to_clean(org_id)

    # 1 ── Qdrant ───────────────────────────────────────────────────────────
    qdrant_points, qdrant_dropped = delete_org_data(org_id)

    # 2 ── PostgreSQL ───────────────────────────────────────────────────────
    pg_counts = purge_org_postgres(org_id)

    # 3 ── on-disk uploaded files ───────────────────────────────────────────
    folders_removed = _delete_drop_folders(rfp_ids)

    # 4 ── in-memory caches ─────────────────────────────────────────────────
    invalidate_org_settings(org_id)
    for run_id in run_ids:
        clear_run_cost(run_id)

    receipt = ErasureReceipt(
        org_id=str(org_id),
        requested_by=requested_by,
        reason=reason,
        erased_at=datetime.now(timezone.utc).isoformat(),
        postgres_deleted=pg_counts,
        qdrant_points_deleted=qdrant_points,
        qdrant_collection_dropped=qdrant_dropped,
        drop_folders_deleted=folders_removed,
        residual_gaps=list(_RESIDUAL_GAPS),
    )

    # 5 ── retained, anonymized receipt ─────────────────────────────────────
    # The destructive steps above have already committed irreversibly, so a
    # failure to persist the receipt row must NOT raise an opaque 500 that
    # discards the counts. Instead we always RETURN the populated receipt (the
    # operator can record it) and flag receipt_persisted=False with a loud error.
    if settings.product.gdpr.keep_erasure_receipt:
        try:
            receipt.receipt_persisted = _write_receipt(receipt)
        except Exception as exc:  # noqa: BLE001 — purge is done; surface, don't lose proof
            log.error(
                "org.erased receipt write FAILED after purge org_id=%s: %s — "
                "returning receipt to caller (receipt_persisted=False)", org_id, exc,
            )
            receipt.receipt_persisted = False

    log.info(
        "org.erased org_id=%s requested_by=%s pg_rows=%d qdrant_points=%d folders=%d",
        org_id, requested_by, sum(pg_counts.values()), qdrant_points, folders_removed,
    )
    return receipt
