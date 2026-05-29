"""
tests/test_deadline_lifecycle.py
=================================
Phase 5 PR-D exit criteria for the deadline scheduler + ingestion sub-graph.

Covers:
  D2 — deadline pass: submission_status flips open -> closed -> processing
  D3 — jobs flip received -> queued -> processing -> facts_ready
  D5 — all facts_ready: rfps.submission_status = 'facts_ready' AND
       event_log row event_type='rfp.facts_ready' created
  D6 — autonomy_mode='auto_to_report' is schema-accepted, scheduler emits
       event_type='rfp.evaluation_failed' reason 'Phase 7 PDF not yet
       implemented' (status still advances to facts_ready)
  D7 — autonomy_mode='manual' RFPs are completely skipped by the scheduler;
       no state transitions, no jobs queued, no event emitted
  D8 — ingestion sub-graph writes setup_id snapshot tag (verified via
       process_job calling extract with the resolved setup_id)

The real ingestion + extraction agents are HEAVY (Qdrant + LLM + PDFs).
These tests inject lightweight stubs via `IngestionAgents` so the scheduler
+ sub-graph orchestration is unit-tested deterministically.

Run:
    python -m pytest tests/test_deadline_lifecycle.py -v
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

_DROPS_ROOT = Path(__file__).parent / "_drops_deadline_test"
_DROPS_ROOT.mkdir(parents=True, exist_ok=True)

from app.db.fact_store import (  # noqa: E402
    create_rfp,
    enqueue_ingestion_job,
    get_engine,
    invite_vendor,
)
from app.jobs.deadline_processor import tick  # noqa: E402
from app.pipeline.ingestion_graph import IngestionAgents, process_job  # noqa: E402


ORG_ID = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _pin_drops_root():
    prev = settings.platform.ingestion.drops_root
    settings.platform.ingestion.drops_root = str(_DROPS_ROOT)
    try:
        yield
    finally:
        settings.platform.ingestion.drops_root = prev


@pytest.fixture
def cleanup():
    """Yields a tracker; cleans up rfps + jobs + setups + event_log + files."""
    rfp_ids: list[str] = []
    setup_ids: list[str] = []

    def add(rfp_id: str, setup_id: str | None = None):
        rfp_ids.append(rfp_id)
        if setup_id:
            setup_ids.append(setup_id)

    yield add

    engine = get_engine()
    with engine.begin() as conn:
        for rid in rfp_ids:
            conn.execute(sa.text("DELETE FROM event_log WHERE rfp_id = :r"), {"r": rid})
            # Break self-FK on ingestion_jobs then drop the rows so the
            # vendor_documents FK on doc_id can be cleared next.
            conn.execute(
                sa.text("UPDATE ingestion_jobs SET superseded_by = NULL, doc_id = NULL WHERE rfp_id = :r"),
                {"r": rid},
            )
            conn.execute(sa.text("DELETE FROM ingestion_jobs WHERE rfp_id = :r"), {"r": rid})
            # Clear extracted_facts then vendor_documents for this rfp.
            conn.execute(
                sa.text(
                    "DELETE FROM extracted_facts WHERE doc_id IN ("
                    "SELECT doc_id FROM vendor_documents WHERE rfp_id = :r)"
                ),
                {"r": rid},
            )
            conn.execute(sa.text("DELETE FROM vendor_documents WHERE rfp_id = :r"), {"r": rid})
            conn.execute(sa.text("DELETE FROM rfps WHERE rfp_id = :r"), {"r": rid})
        for sid in setup_ids:
            conn.execute(sa.text("DELETE FROM evaluation_setups WHERE setup_id = :s"), {"s": sid})


# ── Helpers ──────────────────────────────────────────────────────────


def _seed_evaluation_setup(rfp_id: str, org_id: str = ORG_ID) -> str:
    """Creates a minimal confirmed evaluation_setup row so the ingestion
    sub-graph's _resolve_setup_id() can find it."""
    setup_id = f"setup-{uuid.uuid4().hex[:10]}"
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO evaluation_setups
                    (setup_id, org_id, department, rfp_id, setup_json,
                     confirmed_by, confirmed_at, source)
                VALUES (:sid, :oid, 'IT', :rid, CAST(:sj AS JSONB),
                        'test@meridian', now(), 'rfp_extracted')
                """
            ),
            {
                "sid": setup_id,
                "oid": org_id,
                "rid": rfp_id,
                "sj": json.dumps({"setup_id": setup_id, "rfp_id": rfp_id, "criteria": []}),
            },
        )
    return setup_id


def _drop_file(rfp_id: str, vendor_id: str, content: bytes = b"x") -> str:
    target = _DROPS_ROOT / rfp_id / vendor_id
    target.mkdir(parents=True, exist_ok=True)
    fp = target / "proposal.pdf"
    fp.write_bytes(content)
    return str(fp)


def _seed_received_job(rfp_id: str, vendor_id: str, content: bytes = b"x") -> str:
    """Writes a file + an ingestion_jobs row in status='received'."""
    source_uri = _drop_file(rfp_id, vendor_id, content)
    job_id = enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id=vendor_id,
        content_hash=hex(hash(content) & ((1 << 256) - 1))[2:].rjust(64, "0"),
        filename="proposal.pdf", source_uri=source_uri, status="received",
    )
    assert job_id, "seed received job should not collide"
    return job_id


def _stub_agents(*, fact_count: int = 3, observed: dict | None = None) -> IngestionAgents:
    """Lightweight stubs — no Qdrant / LLM / pypdf."""
    async def ingest(*, content, filename, vendor_id, org_id, rfp_id, setup_id) -> str:
        if observed is not None:
            observed.setdefault("ingest", []).append({
                "vendor_id": vendor_id, "setup_id": setup_id, "rfp_id": rfp_id,
            })
        # Insert a vendor_documents row so the FK on ingestion_jobs.doc_id resolves.
        doc_id = str(uuid.uuid4())
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO vendor_documents
                      (doc_id, org_id, vendor_id, rfp_id, setup_id, filename,
                       content_hash, total_chunks)
                    VALUES (:d, :o, :v, :r, :s, :f, :h, 1)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "d": doc_id, "o": org_id, "v": vendor_id, "r": rfp_id,
                    "s": setup_id, "f": filename,
                    "h": "00" * 32,
                },
            )
        return doc_id

    async def extract(*, doc_id, vendor_id, org_id, rfp_id, setup_id) -> int:
        if observed is not None:
            observed.setdefault("extract", []).append({
                "doc_id": doc_id, "setup_id": setup_id, "vendor_id": vendor_id,
            })
        return fact_count

    return IngestionAgents(ingest=ingest, extract=extract)


# ── D2 ───────────────────────────────────────────────────────────────


def test_deadline_triggers_close(cleanup):
    """D2 — open RFP past deadline -> closed -> processing in one tick."""
    rfp_id = f"phase5d-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    setup_id = _seed_evaluation_setup(rfp_id)
    cleanup(rfp_id, setup_id)
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    _seed_received_job(rfp_id, "acme")

    report = asyncio.run(tick(agents=_stub_agents()))

    assert report.rfps_closed == 1
    assert report.rfps_queued_for_processing == 1
    engine = get_engine()
    with engine.connect() as conn:
        status = conn.execute(
            sa.text("SELECT submission_status FROM rfps WHERE rfp_id = :r"),
            {"r": rfp_id},
        ).scalar()
    assert status == "facts_ready"  # processed all the way in this tick


# ── D3 ───────────────────────────────────────────────────────────────


def test_jobs_advance_through_states(cleanup):
    """D3 — received -> queued -> processing -> facts_ready visible in DB."""
    rfp_id = f"phase5d-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    setup_id = _seed_evaluation_setup(rfp_id)
    cleanup(rfp_id, setup_id)
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    _seed_received_job(rfp_id, "acme", content=b"acme")

    asyncio.run(tick(agents=_stub_agents()))

    engine = get_engine()
    with engine.connect() as conn:
        status = conn.execute(
            sa.text(
                "SELECT status FROM ingestion_jobs WHERE rfp_id = :r"
            ),
            {"r": rfp_id},
        ).scalar()
    assert status == "facts_ready"


# ── D5 ───────────────────────────────────────────────────────────────


def test_facts_ready_emits_event(cleanup):
    """D5 — once all jobs facts_ready, event_log has rfp.facts_ready row."""
    rfp_id = f"phase5d-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    setup_id = _seed_evaluation_setup(rfp_id)
    cleanup(rfp_id, setup_id)
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    invite_vendor(rfp_id=rfp_id, vendor_id="apex", invited_by="a@b")
    _seed_received_job(rfp_id, "acme", content=b"acme")
    _seed_received_job(rfp_id, "apex", content=b"apex")

    report = asyncio.run(tick(agents=_stub_agents()))
    assert report.events_emitted == 1

    engine = get_engine()
    with engine.connect() as conn:
        events = conn.execute(
            sa.text(
                "SELECT event_type, payload FROM event_log "
                "WHERE rfp_id = :r ORDER BY created_at"
            ),
            {"r": rfp_id},
        ).fetchall()
    types = [e.event_type for e in events]
    assert types == ["rfp.facts_ready"]
    assert events[0].payload == {"autonomy_mode": "auto_to_evaluate"}


# ── D6 ───────────────────────────────────────────────────────────────


def test_mode_c_gated(cleanup):
    """D6 — auto_to_report -> 'rfp.evaluation_failed' event, RFP still facts_ready."""
    rfp_id = f"phase5d-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) - timedelta(seconds=30),
        autonomy_mode="auto_to_report",
    )
    setup_id = _seed_evaluation_setup(rfp_id)
    cleanup(rfp_id, setup_id)
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    _seed_received_job(rfp_id, "acme")

    asyncio.run(tick(agents=_stub_agents()))

    engine = get_engine()
    with engine.connect() as conn:
        ev = conn.execute(
            sa.text(
                "SELECT event_type, payload FROM event_log WHERE rfp_id = :r"
            ),
            {"r": rfp_id},
        ).fetchone()
        status = conn.execute(
            sa.text("SELECT submission_status FROM rfps WHERE rfp_id = :r"),
            {"r": rfp_id},
        ).scalar()
    assert ev.event_type == "rfp.evaluation_failed"
    assert ev.payload == {"reason": "Phase 7 PDF not yet implemented"}
    assert status == "facts_ready"


# ── D7 ───────────────────────────────────────────────────────────────


def test_manual_mode_untouched(cleanup):
    """D7 — autonomy_mode='manual' is completely skipped by the scheduler."""
    rfp_id = f"phase5d-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) - timedelta(hours=1),
        autonomy_mode="manual",
    )
    setup_id = _seed_evaluation_setup(rfp_id)
    cleanup(rfp_id, setup_id)
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    _seed_received_job(rfp_id, "acme")

    report = asyncio.run(tick(agents=_stub_agents()))
    assert report.rfps_closed == 0
    assert report.jobs_processed == 0

    engine = get_engine()
    with engine.connect() as conn:
        status = conn.execute(
            sa.text("SELECT submission_status FROM rfps WHERE rfp_id = :r"),
            {"r": rfp_id},
        ).scalar()
        job_status = conn.execute(
            sa.text("SELECT status FROM ingestion_jobs WHERE rfp_id = :r"),
            {"r": rfp_id},
        ).scalar()
        ev_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM event_log WHERE rfp_id = :r"),
            {"r": rfp_id},
        ).scalar()
    assert status == "open"
    assert job_status == "received"
    assert ev_count == 0


# ── D8 ───────────────────────────────────────────────────────────────


def test_setup_id_snapshot(cleanup):
    """D8 — ingest + extract receive the resolved setup_id from the RFP."""
    rfp_id = f"phase5d-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    setup_id = _seed_evaluation_setup(rfp_id)
    cleanup(rfp_id, setup_id)
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    job_id = _seed_received_job(rfp_id, "acme")

    # Pump RFP straight to queued for direct process_job test.
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE rfps SET submission_status='processing' WHERE rfp_id=:r"),
            {"r": rfp_id},
        )
        conn.execute(
            sa.text("UPDATE ingestion_jobs SET status='queued' WHERE job_id=:j"),
            {"j": job_id},
        )

    observed: dict[str, list[dict]] = {}
    result = asyncio.run(process_job(job_id=job_id, agents=_stub_agents(observed=observed)))

    assert result.status == "facts_ready"
    assert observed["ingest"][0]["setup_id"] == setup_id
    assert observed["extract"][0]["setup_id"] == setup_id


# ── Parallel orchestration smoke (informs D4) ────────────────────────


def test_parallel_orchestration_smoke(cleanup):
    """Sanity check: with N stubbed jobs, gather completes; processing count
    matches. NOT the D4 wall-clock benchmark — that requires real agents +
    real PDFs and is documented in PR description as manual integration."""
    rfp_id = f"phase5d-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    setup_id = _seed_evaluation_setup(rfp_id)
    cleanup(rfp_id, setup_id)
    for v in ("a", "b", "c", "d", "e"):
        invite_vendor(rfp_id=rfp_id, vendor_id=v, invited_by="a@b")
        _seed_received_job(rfp_id, v, content=v.encode() * 8)

    report = asyncio.run(tick(agents=_stub_agents()))
    assert report.jobs_processed == 5
    assert report.jobs_failed == 0
