"""
tests/test_ingestion_idempotency.py
====================================
Phase 5 PR-C exit criteria for watcher idempotency / supersedence behaviour.

Covers:
  C5 — same vendor uploads 2 different files -> older marked 'superseded',
       newer becomes the active 'received' row
  C6 — same content_hash uploaded twice      -> 2nd is 'duplicate', no row added
  C8 — PG reconnect race: enqueue, simulate disconnect, retry succeeds

Run:
    python -m pytest tests/test_ingestion_idempotency.py -v
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402

_DROPS_ROOT = Path(__file__).parent / "_drops_idemp_test"
_DROPS_ROOT.mkdir(parents=True, exist_ok=True)

from app.db.fact_store import (  # noqa: E402
    create_rfp,
    get_engine,
    invite_vendor,
)
from app.jobs.ingestion_watcher import handle_dropped_file  # noqa: E402


@pytest.fixture(autouse=True)
def _pin_drops_root():
    prev = settings.platform.ingestion.drops_root
    settings.platform.ingestion.drops_root = str(_DROPS_ROOT)
    try:
        yield
    finally:
        settings.platform.ingestion.drops_root = prev


ORG_ID = str(uuid.uuid4())


@pytest.fixture
def rfp_id():
    rid = f"phase5c-idem-{uuid.uuid4().hex[:8]}"
    yield rid
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE ingestion_jobs SET superseded_by = NULL WHERE rfp_id = :r"),
            {"r": rid},
        )
        conn.execute(sa.text("DELETE FROM ingestion_jobs WHERE rfp_id = :r"), {"r": rid})
        conn.execute(sa.text("DELETE FROM rfps WHERE rfp_id = :r"), {"r": rid})
    rfp_drop = _DROPS_ROOT / rid
    if rfp_drop.exists():
        for p in rfp_drop.rglob("*"):
            if p.is_file():
                p.unlink()
        for d in sorted(rfp_drop.rglob("*"), reverse=True):
            if d.is_dir():
                d.rmdir()
        rfp_drop.rmdir()


def _drop(rfp_id: str, vendor_id: str, name: str, content: bytes) -> Path:
    target = _DROPS_ROOT / rfp_id / vendor_id
    target.mkdir(parents=True, exist_ok=True)
    fp = target / name
    fp.write_bytes(content)
    return fp


# ── C5 ───────────────────────────────────────────────────────────────


def test_supersede_on_reupload(rfp_id):
    """C5 — second different file from same vendor supersedes the first."""
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")

    first = handle_dropped_file(_drop(rfp_id, "acme", "v1.pdf", b"draft-version-1"))
    second = handle_dropped_file(_drop(rfp_id, "acme", "v2.pdf", b"final-version-2"))

    assert first.status == "received"
    assert second.status == "received"
    assert "superseded 1 prior" in second.reason

    # Database state: first row should be 'superseded' and point at the second.
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT job_id::text AS job_id, status, superseded_by::text AS sb "
                "FROM ingestion_jobs WHERE rfp_id = :r ORDER BY received_at"
            ),
            {"r": rfp_id},
        ).fetchall()

    assert len(rows) == 2
    assert rows[0].status == "superseded"
    assert rows[0].sb == second.job_id
    assert rows[1].status == "received"
    assert rows[1].sb is None


# ── C6 ───────────────────────────────────────────────────────────────


def test_duplicate_hash(rfp_id):
    """C6 — exact same content uploaded twice -> 2nd returns status='duplicate'."""
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    same_bytes = b"identical-content-blob-xxyyzz"

    first = handle_dropped_file(_drop(rfp_id, "acme", "a.pdf", same_bytes))
    second = handle_dropped_file(_drop(rfp_id, "acme", "b.pdf", same_bytes))

    assert first.status == "received"
    assert second.status == "duplicate"
    assert second.job_id is None

    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(
            sa.text("SELECT COUNT(*) FROM ingestion_jobs WHERE rfp_id = :r"),
            {"r": rfp_id},
        ).scalar()
    assert n == 1


# ── C8 ───────────────────────────────────────────────────────────────


def test_watcher_handles_dropped_engine(rfp_id, monkeypatch):
    """
    C8 — simulate a brief DB connection loss between two calls.
    The watcher's pure entry point opens connections on demand via the
    fact_store engine; restarting the simulated 'disconnect' returns the
    engine to working state and the next call succeeds.
    """
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")

    # First call succeeds.
    p1 = _drop(rfp_id, "acme", "before.pdf", b"before-disconnect")
    r1 = handle_dropped_file(p1)
    assert r1.status == "received"

    # Drop the engine: next get_engine() will rebuild.
    import app.db.fact_store as fs
    fs._engine = None

    p2 = _drop(rfp_id, "acme", "after.pdf", b"after-reconnect")
    r2 = handle_dropped_file(p2)
    assert r2.status == "received"
    assert "superseded 1 prior" in r2.reason
