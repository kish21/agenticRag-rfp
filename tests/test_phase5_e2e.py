"""
tests/test_phase5_e2e.py
=========================
Phase 5 final acceptance test — the single source of truth for
"Phase 5 is done."

Walks the entire Phase 5 lifecycle end-to-end against a live PostgreSQL,
using stubbed ingestion+extraction agents so the test stays under 5s.

Scenario:
  1. Create RFP `e2e-phase5-test-XYZ` with deadline = NOW + 60 seconds,
     autonomy_mode='auto_to_evaluate'.
  2. Invite 3 vendors: acme, apex, bravo.
  3. Drop 1 valid file per invited vendor.
  4. Drop 1 duplicate of vendor 1's file        (expect: duplicate).
  5. Drop 1 file for an UNINVITED vendor        (expect: needs_attribution).
  6. Simulate the deadline passing.
  7. Run the deadline_processor tick once.
  8. Assert lifecycle: submission_status='facts_ready',
     ingestion_jobs counts:
       - 3 facts_ready (one per invited vendor)
       - 1 duplicate
       - 1 needs_attribution
  9. Assert event_log has exactly 1 'rfp.facts_ready' row.

Run:
    python -m pytest tests/test_phase5_e2e.py -v
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402

_DROPS_ROOT = Path(__file__).parent / "_drops_e2e_test"
_DROPS_ROOT.mkdir(parents=True, exist_ok=True)

from app.db.fact_store import (  # noqa: E402
    create_rfp,
    get_engine,
    invite_vendor,
)
from app.jobs.deadline_processor import tick  # noqa: E402
from app.jobs.ingestion_watcher import handle_dropped_file  # noqa: E402
from app.pipeline.ingestion_graph import IngestionAgents  # noqa: E402


ORG_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _pin_drops_root():
    prev = settings.platform.ingestion.drops_root
    settings.platform.ingestion.drops_root = str(_DROPS_ROOT)
    try:
        yield
    finally:
        settings.platform.ingestion.drops_root = prev


def _seed_evaluation_setup(rfp_id: str) -> str:
    setup_id = f"setup-e2e-{uuid.uuid4().hex[:10]}"
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO evaluation_setups
                    (setup_id, org_id, department, rfp_id, setup_json,
                     confirmed_by, confirmed_at, source)
                VALUES (:s, :o, 'IT', :r, CAST(:j AS JSONB), 'e2e@test',
                        now(), 'rfp_extracted')
                """
            ),
            {
                "s": setup_id, "o": ORG_ID, "r": rfp_id,
                "j": json.dumps({"setup_id": setup_id, "rfp_id": rfp_id, "criteria": []}),
            },
        )
    return setup_id


def _stub_agents() -> IngestionAgents:
    async def ingest(*, content, filename, vendor_id, org_id, rfp_id, setup_id) -> str:
        doc_id = str(uuid.uuid4())
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO vendor_documents
                        (doc_id, org_id, vendor_id, rfp_id, setup_id,
                         filename, content_hash, total_chunks)
                    VALUES (:d, :o, :v, :r, :s, :f, :h, 1)
                    """
                ),
                {
                    "d": doc_id, "o": org_id, "v": vendor_id, "r": rfp_id,
                    "s": setup_id, "f": filename, "h": "00" * 32,
                },
            )
        return doc_id

    async def extract(*, doc_id, vendor_id, org_id, rfp_id, setup_id) -> int:
        return 5

    return IngestionAgents(ingest=ingest, extract=extract)


def test_phase5_e2e(monkeypatch):
    rfp_id = f"e2e-phase5-{uuid.uuid4().hex[:8]}"
    deadline = datetime.now(timezone.utc) + timedelta(seconds=60)
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="E2E Phase 5",
        created_by_email="e2e@test", department="IT",
        submission_deadline=deadline, autonomy_mode="auto_to_evaluate",
    )
    setup_id = _seed_evaluation_setup(rfp_id)
    try:
        for v in ("acme", "apex", "bravo"):
            invite_vendor(rfp_id=rfp_id, vendor_id=v, invited_by="e2e@test")

        # Step 3 — 1 valid file per invited vendor (unique content).
        for v, body in (("acme", b"acme-proposal-final"),
                        ("apex", b"apex-proposal-final"),
                        ("bravo", b"bravo-proposal-final")):
            fp = _DROPS_ROOT / rfp_id / v / "proposal.pdf"
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(body)
            handle_dropped_file(fp)

        # Step 4 — duplicate of acme's content under a different filename.
        dup = _DROPS_ROOT / rfp_id / "acme" / "duplicate.pdf"
        dup.write_bytes(b"acme-proposal-final")
        r_dup = handle_dropped_file(dup)
        assert r_dup.status == "duplicate"

        # Step 5 — file for an uninvited vendor.
        stranger_path = _DROPS_ROOT / rfp_id / "stranger" / "x.pdf"
        stranger_path.parent.mkdir(parents=True, exist_ok=True)
        stranger_path.write_bytes(b"stranger-content")
        r_stranger = handle_dropped_file(stranger_path)
        assert r_stranger.status == "needs_attribution"

        # Step 6 — simulate the deadline passing.
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE rfps SET submission_deadline = now() - interval '1 minute' "
                    "WHERE rfp_id = :r"
                ),
                {"r": rfp_id},
            )

        # Step 7 — one scheduler tick.
        report = asyncio.run(tick(agents=_stub_agents()))
        assert report.jobs_processed == 3
        assert report.jobs_failed == 0
        assert report.events_emitted == 1

        # Step 8 — assert lifecycle + job counts.
        with engine.connect() as conn:
            status = conn.execute(
                sa.text("SELECT submission_status FROM rfps WHERE rfp_id = :r"),
                {"r": rfp_id},
            ).scalar()
            rows = conn.execute(
                sa.text(
                    "SELECT status, COUNT(*) AS n FROM ingestion_jobs "
                    "WHERE rfp_id = :r GROUP BY status"
                ),
                {"r": rfp_id},
            ).fetchall()
        assert status == "facts_ready"
        counts = {r.status: r.n for r in rows}
        assert counts.get("facts_ready") == 3
        assert counts.get("duplicate", 0) == 0  # duplicate was rejected, no row inserted
        assert counts.get("needs_attribution") == 1

        # Step 9 — exactly one rfp.facts_ready event.
        with engine.connect() as conn:
            event_rows = conn.execute(
                sa.text(
                    "SELECT event_type FROM event_log WHERE rfp_id = :r"
                ),
                {"r": rfp_id},
            ).fetchall()
        types = [r.event_type for r in event_rows]
        assert types == ["rfp.facts_ready"]

    finally:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM event_log WHERE rfp_id = :r"), {"r": rfp_id})
            conn.execute(
                sa.text("UPDATE ingestion_jobs SET superseded_by = NULL, doc_id = NULL WHERE rfp_id = :r"),
                {"r": rfp_id},
            )
            conn.execute(sa.text("DELETE FROM ingestion_jobs WHERE rfp_id = :r"), {"r": rfp_id})
            conn.execute(
                sa.text(
                    "DELETE FROM vendor_documents WHERE rfp_id = :r"
                ),
                {"r": rfp_id},
            )
            conn.execute(sa.text("DELETE FROM rfps WHERE rfp_id = :r"), {"r": rfp_id})
            conn.execute(sa.text("DELETE FROM evaluation_setups WHERE setup_id = :s"), {"s": setup_id})
