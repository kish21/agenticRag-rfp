"""
tests/test_phase5_schema.py
============================
Phase 5 PR-A exit criteria.

Verifies the four new tables (rfps, invited_vendors, ingestion_jobs, event_log),
their CHECK / UNIQUE constraints, the fact_store helper functions, and the
Pydantic RFP domain model.

Requires running Postgres (see docker-compose.yml). Cleans up its own
fixture data on teardown.

Run:
    python -m pytest tests/test_phase5_schema.py -v
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.fact_store import (  # noqa: E402
    create_rfp,
    emit_event,
    enqueue_ingestion_job,
    facts_already_extracted,
    get_engine,
    get_rfp_rollup,
    invite_vendor,
    mark_rfp_facts_ready,
    set_deadline,
)
from app.domain.rfp import RFP, IngestionJob, can_transition  # noqa: E402


ORG_ID = str(uuid.uuid4())


def _hash(seed: str) -> str:
    """Deterministic 64-char hash from seed string."""
    import hashlib
    return hashlib.sha256(seed.encode()).hexdigest()


@pytest.fixture
def rfp_id():
    """Yields a fresh rfp_id and cascades cleanup of all phase-5 rows on teardown."""
    rid = f"phase5-test-{uuid.uuid4().hex[:8]}"
    yield rid
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM event_log WHERE rfp_id = :r"), {"r": rid})
        conn.execute(sa.text("DELETE FROM ingestion_jobs WHERE rfp_id = :r"), {"r": rid})
        conn.execute(sa.text("DELETE FROM rfps WHERE rfp_id = :r"), {"r": rid})


# ── A3: submission_status CHECK constraint ───────────────────────────

def test_invalid_submission_status_rejected(rfp_id):
    """A3 — CHECK constraint rejects unknown submission_status values."""
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="x",
        created_by_email="a@b", autonomy_mode="auto_to_evaluate",
    )
    engine = get_engine()
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE rfps SET submission_status = 'banana' WHERE rfp_id = :r"),
                {"r": rfp_id},
            )


# ── A4: autonomy_mode CHECK constraint ───────────────────────────────

def test_invalid_autonomy_mode_rejected(rfp_id):
    """A4 — CHECK constraint rejects unknown autonomy_mode values."""
    engine = get_engine()
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO rfps (rfp_id, org_id, title, created_by_email, autonomy_mode)
                    VALUES (:r, :o, 't', 'a@b', 'turbo')
                    """
                ),
                {"r": rfp_id, "o": ORG_ID},
            )


# ── A5: ingestion_jobs UNIQUE constraint ─────────────────────────────

def test_duplicate_content_hash_rejected(rfp_id):
    """A5 — second enqueue with same (rfp_id, vendor_id, content_hash) returns None."""
    create_rfp(rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b")
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    h = _hash("file-1")
    first = enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id="acme",
        content_hash=h, filename="f.pdf",
    )
    second = enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id="acme",
        content_hash=h, filename="f.pdf",
    )
    assert first is not None
    assert second is None  # ON CONFLICT DO NOTHING


# ── A6: helper functions — create_rfp + invite_vendor ────────────────

def test_create_rfp_and_invite_vendor(rfp_id):
    """A6.1 — create_rfp + invite_vendor write expected rows."""
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="IT Managed Services",
        created_by_email="proc@meridian.com", department="IT",
        autonomy_mode="auto_to_evaluate",
    )
    invite_vendor(
        rfp_id=rfp_id, vendor_id="acme", vendor_name="Acme Corp",
        invited_by="proc@meridian.com",
    )
    engine = get_engine()
    with engine.connect() as conn:
        rfp_row = conn.execute(
            sa.text("SELECT autonomy_mode, submission_status FROM rfps WHERE rfp_id = :r"),
            {"r": rfp_id},
        ).fetchone()
        vendor_row = conn.execute(
            sa.text("SELECT vendor_name FROM invited_vendors WHERE rfp_id = :r"),
            {"r": rfp_id},
        ).fetchone()
    assert rfp_row.autonomy_mode == "auto_to_evaluate"
    assert rfp_row.submission_status == "open"
    assert vendor_row.vendor_name == "Acme Corp"


def test_invite_vendor_idempotent(rfp_id):
    """A6.2 — invite_vendor twice does not raise; only one row remains."""
    create_rfp(rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b")
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    engine = get_engine()
    with engine.connect() as conn:
        count = conn.execute(
            sa.text("SELECT COUNT(*) FROM invited_vendors WHERE rfp_id = :r"),
            {"r": rfp_id},
        ).scalar()
    assert count == 1


def test_set_deadline_blocks_after_close(rfp_id):
    """A6.3 — set_deadline succeeds while open, fails once status flipped."""
    create_rfp(rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b")
    future = datetime.now(timezone.utc) + timedelta(days=14)
    assert set_deadline(rfp_id=rfp_id, submission_deadline=future) is True

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE rfps SET submission_status = 'closed' WHERE rfp_id = :r"),
            {"r": rfp_id},
        )
    later = datetime.now(timezone.utc) + timedelta(days=30)
    assert set_deadline(rfp_id=rfp_id, submission_deadline=later) is False


def test_mark_rfp_facts_ready(rfp_id):
    """A6.4 — mark_rfp_facts_ready transitions processing → facts_ready."""
    create_rfp(rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b")
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE rfps SET submission_status = 'processing' WHERE rfp_id = :r"),
            {"r": rfp_id},
        )
    mark_rfp_facts_ready(rfp_id=rfp_id)
    with engine.connect() as conn:
        status = conn.execute(
            sa.text("SELECT submission_status FROM rfps WHERE rfp_id = :r"),
            {"r": rfp_id},
        ).scalar()
    assert status == "facts_ready"


def test_emit_event_writes_row(rfp_id):
    """A6.5 — emit_event inserts an event_log row with the given type + payload."""
    create_rfp(rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b")
    event_id = emit_event(
        event_type="rfp.facts_ready", org_id=ORG_ID, rfp_id=rfp_id,
        payload={"vendor_count": 3},
    )
    assert event_id
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT event_type, payload, delivered_at "
                "FROM event_log WHERE event_id = :e"
            ),
            {"e": event_id},
        ).fetchone()
    assert row.event_type == "rfp.facts_ready"
    assert row.payload == {"vendor_count": 3}
    assert row.delivered_at is None


def test_get_rfp_rollup(rfp_id):
    """A6.6 — get_rfp_rollup returns expected aggregates."""
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        autonomy_mode="manual",
    )
    invite_vendor(rfp_id=rfp_id, vendor_id="v1", invited_by="a@b")
    invite_vendor(rfp_id=rfp_id, vendor_id="v2", invited_by="a@b")
    enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id="v1",
        content_hash=_hash("a"), status="received",
    )
    enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id="v2",
        content_hash=_hash("b"), status="duplicate",
    )
    rollup = get_rfp_rollup(rfp_id=rfp_id)
    assert rollup["vendor_count"] == 2
    assert rollup["autonomy_mode"] == "manual"
    assert rollup["job_counts_by_status"] == {"received": 1, "duplicate": 1}


def test_facts_already_extracted_false_when_empty(rfp_id):
    """A6.7 — facts_already_extracted returns False for fresh RFP."""
    create_rfp(rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b")
    assert facts_already_extracted(rfp_id=rfp_id, vendor_id="acme") is False


# ── A7: Pydantic RFP model validates enums ───────────────────────────

def test_rfp_model_validation():
    """A7 — Pydantic RFP model rejects invalid enum values; can_transition() works."""
    valid = RFP(
        rfp_id="r1",
        org_id=uuid.uuid4(),
        title="t",
        created_by_email="a@b",
    )
    assert valid.submission_status == "open"
    assert valid.autonomy_mode == "auto_to_evaluate"

    with pytest.raises(ValidationError):
        RFP(
            rfp_id="r1", org_id=uuid.uuid4(), title="t",
            created_by_email="a@b", autonomy_mode="turbo",
        )
    with pytest.raises(ValidationError):
        RFP(
            rfp_id="r1", org_id=uuid.uuid4(), title="t",
            created_by_email="a@b", submission_status="banana",
        )

    # IngestionJob content_hash length enforced
    with pytest.raises(ValidationError):
        IngestionJob(
            job_id=uuid.uuid4(), org_id=uuid.uuid4(), rfp_id="r",
            vendor_id="v", content_hash="too-short", status="received",
        )

    # Transition helper
    assert can_transition("open", "closed") is True
    assert can_transition("open", "facts_ready") is False
    assert can_transition("evaluated", "open") is False
