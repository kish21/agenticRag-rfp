"""
Live end-to-end smoke for GDPR Mode B tenant erasure (SC-001 #119).

Unlike tests/test_org_erasure_gdpr.py (which mocks Qdrant), this exercises the
REAL path against a running stack: real Qdrant collection + points, real on-disk
drop folder, real PostgreSQL rows, and the real delete_org_data — NO mocks, NO
pytest conftest owner-engine override. Proves the wired path actually erases.

Run (docker postgres + qdrant must be up):
    PYTHONUTF8=1 python -m tools.live_erasure_smoke
Exit 0 = all assertions passed.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import sqlalchemy as sa
from qdrant_client.models import PointStruct

from app.config import settings
from app.db.fact_store import get_admin_engine
from app.domain.org_erasure import erase_org
from app.retrieval.qdrant import (
    create_collection, get_qdrant_client, org_collection_name,
)

VSIZE = 8  # tiny dense vector — avoids any embedding-provider call


def _seed_qdrant(org_id: str, vendor_id: str) -> str:
    name = org_collection_name(org_id)
    client = get_qdrant_client()
    create_collection(name, vector_size=VSIZE, client=client)
    pts = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector={"dense": [0.1 * (i + 1)] * VSIZE},
            payload={"org_id": org_id, "vendor_id": vendor_id, "text": f"chunk {i}"},
        )
        for i in range(3)
    ]
    client.upsert(collection_name=name, points=pts)
    return name


def _seed_postgres(org_id: str, rfp_id: str, run_id: str) -> None:
    eng = get_admin_engine()
    with eng.begin() as c:
        c.execute(sa.text("INSERT INTO organisations (org_id, org_name) "
                          "VALUES (CAST(:o AS uuid), :n)"),
                  {"o": org_id, "n": "LIVE Erasure Smoke Org"})
        c.execute(sa.text("INSERT INTO rfps (rfp_id, org_id, title, created_by_email) "
                          "VALUES (:r, CAST(:o AS uuid), 'RFP', 'live@smoke.test')"),
                  {"r": rfp_id, "o": org_id})
        c.execute(sa.text("INSERT INTO evaluation_runs (run_id, org_id, rfp_id, status) "
                          "VALUES (CAST(:run AS uuid), CAST(:o AS uuid), :r, 'completed')"),
                  {"run": run_id, "o": org_id, "r": rfp_id})


def _qdrant_collection_exists(name: str) -> bool:
    client = get_qdrant_client()
    return name in [c.name for c in client.get_collections().collections]


def _pg_org_exists(org_id: str) -> bool:
    with get_admin_engine().connect() as c:
        return c.execute(sa.text("SELECT 1 FROM organisations WHERE org_id = CAST(:o AS uuid)"),
                         {"o": org_id}).fetchone() is not None


def main() -> int:
    org_id = str(uuid.uuid4())
    rfp_id = f"rfp-{uuid.uuid4().hex}"
    run_id = str(uuid.uuid4())
    vendor_id = "acme"
    failures: list[str] = []

    print(f"[seed] org_id={org_id}")
    coll = _seed_qdrant(org_id, vendor_id)
    _seed_postgres(org_id, rfp_id, run_id)

    drops_root = Path(settings.platform.ingestion.drops_root)
    folder = drops_root / rfp_id
    (folder / vendor_id).mkdir(parents=True, exist_ok=True)
    (folder / vendor_id / "proposal.pdf").write_bytes(b"%PDF-1.4 live smoke")

    # Pre-conditions
    assert _qdrant_collection_exists(coll), "seed failed: qdrant collection missing"
    assert _pg_org_exists(org_id), "seed failed: org row missing"
    assert folder.exists(), "seed failed: drop folder missing"
    pts_before = get_qdrant_client().count(collection_name=coll, exact=True).count
    print(f"[seed] qdrant points={pts_before}, collection={coll}, folder={folder}")

    # ── REAL erasure (no mocks) ──────────────────────────────────────────
    receipt = erase_org(org_id, requested_by="live@smoke.test",
                        reason="live end-to-end erasure verification")
    print(f"[erase] receipt: qdrant_points={receipt.qdrant_points_deleted} "
          f"dropped={receipt.qdrant_collection_dropped} "
          f"folders={receipt.drop_folders_deleted} "
          f"pg_rows={sum(receipt.postgres_deleted.values())} "
          f"persisted={receipt.receipt_persisted}")

    # ── Assertions on the live stores ────────────────────────────────────
    if _qdrant_collection_exists(coll):
        failures.append(f"Qdrant collection {coll} still exists")
    if receipt.qdrant_points_deleted != pts_before:
        failures.append(f"qdrant_points_deleted={receipt.qdrant_points_deleted} != seeded {pts_before}")
    if not receipt.qdrant_collection_dropped:
        failures.append("qdrant_collection_dropped is False")
    if folder.exists():
        failures.append(f"drop folder {folder} still exists on disk")
    if receipt.drop_folders_deleted != 1:
        failures.append(f"drop_folders_deleted={receipt.drop_folders_deleted} != 1")
    if _pg_org_exists(org_id):
        failures.append("organisations row still exists in PostgreSQL")
    if receipt.postgres_deleted.get("organisations") != 1:
        failures.append("receipt did not count the organisations delete")
    if not receipt.receipt_persisted:
        failures.append("receipt_persisted is False")

    # Receipt row really landed in audit_log and survives the org delete
    with get_admin_engine().connect() as c:
        rows = c.execute(sa.text(
            "SELECT event_type, actor FROM audit_log WHERE org_id = CAST(:o AS uuid)"),
            {"o": org_id}).fetchall()
    if not (len(rows) == 1 and rows[0][0] == "org.erased" and rows[0][1] == "live@smoke.test"):
        failures.append(f"expected exactly one org.erased receipt row, got {rows}")

    # cleanup the retained receipt so the smoke leaves nothing behind
    with get_admin_engine().begin() as c:
        c.execute(sa.text("DELETE FROM audit_log WHERE org_id = CAST(:o AS uuid)"), {"o": org_id})

    if failures:
        print("\n[FAIL] live erasure smoke:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n[PASS] live erasure smoke — Qdrant + disk + PostgreSQL all wiped, receipt retained.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
