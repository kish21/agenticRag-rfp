"""
tests/test_ingestion_attribution.py
====================================
Phase 5 PR-C exit criteria for the watcher attribution layer.

Covers:
  C2 — file before deadline at drops/{rfp_id}/{vendor_id}/ -> status='received'
  C3 — file after deadline                                  -> status='rejected_late'
  C4 — file for uninvited vendor                            -> status='needs_attribution'
  C7 — file at rfp_id root (no vendor folder)              -> status='needs_attribution'
        (LLM-fallback path is exercised in test_llm_attribution_*)

Drives the watcher's pure entry point `handle_dropped_file()` directly;
does not spawn watchdog so tests stay synchronous + fast.

Run:
    python -m pytest tests/test_ingestion_attribution.py -v
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

_DROPS_ROOT = Path(__file__).parent / "_drops_watcher_test"
_DROPS_ROOT.mkdir(parents=True, exist_ok=True)

from app.db.fact_store import (  # noqa: E402
    create_rfp,
    get_engine,
    invite_vendor,
)
from app.jobs.ingestion_watcher import handle_dropped_file  # noqa: E402


@pytest.fixture(autouse=True)
def _pin_drops_root():
    """Pin drops_root for every test in this module — other test files
    mutate settings.platform.ingestion.drops_root at import time."""
    prev = settings.platform.ingestion.drops_root
    settings.platform.ingestion.drops_root = str(_DROPS_ROOT)
    try:
        yield
    finally:
        settings.platform.ingestion.drops_root = prev


ORG_ID = str(uuid.uuid4())


@pytest.fixture
def rfp_id():
    rid = f"phase5c-{uuid.uuid4().hex[:8]}"
    yield rid
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM ingestion_jobs WHERE rfp_id = :r"), {"r": rid})
        conn.execute(sa.text("DELETE FROM rfps WHERE rfp_id = :r"), {"r": rid})
    # Best-effort filesystem cleanup
    rfp_drop = _DROPS_ROOT / rid
    if rfp_drop.exists():
        for p in rfp_drop.rglob("*"):
            if p.is_file():
                p.unlink()
        for d in sorted(rfp_drop.rglob("*"), reverse=True):
            if d.is_dir():
                d.rmdir()
        rfp_drop.rmdir()


def _drop(rfp_id: str, vendor_id: str | None, name: str, content: bytes = b"hello") -> Path:
    """Writes a file at drops/{rfp_id}/[{vendor_id}/]/{name} and returns its Path."""
    target_dir = _DROPS_ROOT / rfp_id
    if vendor_id is not None:
        target_dir = target_dir / vendor_id
    target_dir.mkdir(parents=True, exist_ok=True)
    fp = target_dir / name
    fp.write_bytes(content)
    return fp


# ── C2 ───────────────────────────────────────────────────────────────


def test_path_based_attribution(rfp_id):
    """C2 — file before deadline in invited vendor folder -> status='received'."""
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    path = _drop(rfp_id, "acme", "proposal.pdf", content=b"acme-proposal-v1")

    result = handle_dropped_file(path)
    assert result.status == "received"
    assert result.rfp_id == rfp_id
    assert result.vendor_id == "acme"
    assert result.job_id

    # No extracted_facts rows created.
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(
            sa.text("SELECT COUNT(*) FROM extracted_facts WHERE vendor_id = 'acme'")
        ).scalar()
    assert n == 0


# ── C3 ───────────────────────────────────────────────────────────────


def test_late_rejection_past_deadline(rfp_id):
    """C3 — file dropped AFTER deadline -> status='rejected_late'."""
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    path = _drop(rfp_id, "acme", "late.pdf", content=b"late-file")

    result = handle_dropped_file(path)
    assert result.status == "rejected_late"
    assert result.reason == "past deadline"


def test_late_rejection_status_closed(rfp_id):
    """C3.2 — file dropped after submission_status flipped to closed."""
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE rfps SET submission_status='closed' WHERE rfp_id=:r"),
            {"r": rfp_id},
        )
    path = _drop(rfp_id, "acme", "after_close.pdf")
    result = handle_dropped_file(path)
    assert result.status == "rejected_late"
    assert "submission_status=closed" in result.reason


# ── C4 ───────────────────────────────────────────────────────────────


def test_uninvited_vendor(rfp_id):
    """C4 — file under an uninvited vendor folder -> status='needs_attribution'."""
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    path = _drop(rfp_id, "stranger", "proposal.pdf", content=b"who-is-this")

    result = handle_dropped_file(path)
    assert result.status == "needs_attribution"
    assert result.vendor_id == "stranger"
    assert "invited_vendors" in result.reason


# ── C7 ───────────────────────────────────────────────────────────────


def test_root_drop_needs_attribution(rfp_id):
    """C7 — file at rfp_id root with no vendor folder -> needs_attribution."""
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    path = _drop(rfp_id, None, "mystery.pdf", content=b"ambiguous-file")

    result = handle_dropped_file(path)
    assert result.status == "needs_attribution"
    assert result.vendor_id is None
    assert "LLM attribution" in result.reason


def test_orphan_unknown_rfp_id(rfp_id):
    """File whose rfp_id has no rfps row is ignored (no FK leak)."""
    bogus_path = _drop("does-not-exist-rfp", "acme", "x.pdf", content=b"orphan")
    try:
        result = handle_dropped_file(bogus_path)
        assert result.status == "needs_attribution"
        assert result.job_id is None
    finally:
        # cleanup
        bogus_root = _DROPS_ROOT / "does-not-exist-rfp"
        for p in bogus_root.rglob("*"):
            if p.is_file():
                p.unlink()
        for d in sorted(bogus_root.rglob("*"), reverse=True):
            if d.is_dir():
                d.rmdir()
        bogus_root.rmdir()
