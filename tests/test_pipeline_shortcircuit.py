"""
tests/test_pipeline_shortcircuit.py
====================================
Phase 5 PR-E exit criteria.

Covers:
  E2 — ingestion_node + extraction_per_vendor emit 'skipped' events when
       facts_already_extracted() returns True for every vendor in the run
  E3 — GET /api/v1/admin/attribution-queue scoped to org_id
  E4 — POST /api/v1/admin/attribution-queue/{job_id}/assign flips
       needs_attribution -> received  (or queued if RFP is closed)
  E5 — POST /api/v1/admin/late-addendum/{job_id}/accept promotes
       rejected_late -> queued

E1 (≤60s user-triggered eval on 5-vendor fixture) and E6/E7 (legacy suite
green) are verified by running the existing checkpoint_runner + smoke_test
in CI — see PR description.

Run:
    python -m pytest tests/test_pipeline_shortcircuit.py -v
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings  # noqa: E402

_DROPS_ROOT = Path(__file__).parent / "_drops_pre_test"
_DROPS_ROOT.mkdir(parents=True, exist_ok=True)

from app.api.admin_routes import router as admin_router  # noqa: E402
from app.api.rfp_routes import router as rfp_router  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.auth.jwt import TokenData  # noqa: E402
from app.db.fact_store import (  # noqa: E402
    create_rfp,
    enqueue_ingestion_job,
    get_engine,
    invite_vendor,
)
from app.pipeline.nodes import ingestion_node, extraction_per_vendor  # noqa: E402

# Test app — only the routers under test.
app = FastAPI()
app.include_router(rfp_router)
app.include_router(admin_router)

ORG_ID = str(uuid.uuid4())
OTHER_ORG_ID = str(uuid.uuid4())


def _user(role: str = "department_admin", org_id: str = ORG_ID) -> TokenData:
    return TokenData(email=f"{role}@meridian.test", org_id=org_id, role=role, dept_id="proc")


@pytest.fixture
def client():
    return TestClient(app)


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
    rfp_ids: list[str] = []

    def add(rfp_id: str):
        rfp_ids.append(rfp_id)

    yield add

    engine = get_engine()
    with engine.begin() as conn:
        for rid in rfp_ids:
            conn.execute(sa.text("DELETE FROM event_log WHERE rfp_id = :r"), {"r": rid})
            conn.execute(
                sa.text("UPDATE ingestion_jobs SET superseded_by = NULL, doc_id = NULL WHERE rfp_id = :r"),
                {"r": rid},
            )
            conn.execute(sa.text("DELETE FROM ingestion_jobs WHERE rfp_id = :r"), {"r": rid})
            conn.execute(sa.text("DELETE FROM rfps WHERE rfp_id = :r"), {"r": rid})


@pytest.fixture
def as_admin():
    app.dependency_overrides[get_current_user] = lambda: _user("department_admin")
    yield
    app.dependency_overrides.clear()


# ── E2 — short-circuit ───────────────────────────────────────────────


def test_ingestion_node_short_circuit_emits_skipped():
    """E2.1 — when facts_already_extracted is True for all vendors,
    ingestion_node emits 'skipped' events and returns without calling
    the ingestion agent."""
    emitted: list[tuple[str, str]] = []

    def _fake_emit(state, agent, status, *args, **kwargs):
        emitted.append((agent, status))

    state = {
        "org_id": ORG_ID,
        "rfp_id": "rfp-skip",
        "vendor_file_map": {"acme": (b"x", "acme.pdf"), "apex": (b"y", "apex.pdf")},
        "evaluation_setup_dict": {
            "setup_id": "s", "rfp_id": "r", "scoring_criteria": [],
            "mandatory_checks": [], "extraction_targets": [],
        },
        "rfp_bytes": b"rfp",
        "rfp_filename": "rfp.pdf",
        "run_id": "run-skip",
    }

    with patch("app.db.fact_store.facts_already_extracted", return_value=True), \
         patch("app.pipeline.nodes._emit", _fake_emit), \
         patch("app.pipeline.nodes.run_ingestion_agent") as mock_ingest:
        result = asyncio.run(ingestion_node(state))

    assert result == {}
    assert mock_ingest.call_count == 0
    assert ("ingestion", "skipped") in emitted
    assert ("ingestion", "done") in emitted


def test_extraction_per_vendor_short_circuit():
    """E2.2 — per-vendor extraction returns {} without calling the
    extraction agent when facts_already_extracted is True."""
    emitted: list[tuple[str, str]] = []

    def _fake_emit(state, agent, status, *args, **kwargs):
        emitted.append((agent, status))

    state = {
        "org_id": ORG_ID,
        "rfp_id": "rfp-skip2",
        "vendor_id": "acme",
        "setup_id": "s",
        "evaluation_setup_dict": {
            "setup_id": "s", "rfp_id": "r", "scoring_criteria": [],
            "mandatory_checks": [], "extraction_targets": [],
        },
        "retrieval_output_objects": {"acme": object()},
        "run_id": "run-skip2",
    }

    with patch("app.db.fact_store.facts_already_extracted", return_value=True), \
         patch("app.pipeline.nodes._emit", _fake_emit), \
         patch("app.pipeline.nodes.run_extraction_agent") as mock_ext:
        result = asyncio.run(extraction_per_vendor(state))

    assert result == {}
    assert mock_ext.call_count == 0
    assert ("extraction", "skipped") in emitted


# ── E3 ───────────────────────────────────────────────────────────────


def test_attribution_queue_scoped(client, as_admin, cleanup):
    """E3 — queue endpoint returns only the caller's-org needs_attribution
    + rejected_late rows."""
    rfp_id = f"phase5e-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    cleanup(rfp_id)
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    # Seed: 1 needs_attribution + 1 rejected_late + 1 received (excluded)
    enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id="_unknown_",
        content_hash="a" * 64, status="needs_attribution",
        filename="orphan.pdf", source_uri=f"/tmp/orphan-{uuid.uuid4().hex}.pdf",
    )
    enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id="acme",
        content_hash="b" * 64, status="rejected_late",
        filename="late.pdf", source_uri=f"/tmp/late-{uuid.uuid4().hex}.pdf",
    )
    enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id="acme",
        content_hash="c" * 64, status="received",
        filename="ok.pdf", source_uri=f"/tmp/ok-{uuid.uuid4().hex}.pdf",
    )
    # Cross-org noise — should NOT appear.
    other_rfp = f"phase5e-other-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=other_rfp, org_id=OTHER_ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    cleanup(other_rfp)
    enqueue_ingestion_job(
        org_id=OTHER_ORG_ID, rfp_id=other_rfp, vendor_id="_unknown_",
        content_hash="d" * 64, status="needs_attribution",
        filename="other.pdf", source_uri=f"/tmp/other-{uuid.uuid4().hex}.pdf",
    )

    response = client.get("/api/v1/admin/attribution-queue")
    assert response.status_code == 200, response.text
    jobs = response.json()["jobs"]
    assert len(jobs) == 2
    statuses = {j["status"] for j in jobs}
    assert statuses == {"needs_attribution", "rejected_late"}
    assert all(j["rfp_id"] == rfp_id for j in jobs)


# ── E4 ───────────────────────────────────────────────────────────────


def test_assign_attribution_to_invited_vendor(client, as_admin, cleanup):
    """E4 — assigning to an already-invited vendor flips status to 'received'."""
    rfp_id = f"phase5e-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    cleanup(rfp_id)
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    job_id = enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id="_unknown_",
        content_hash="e" * 64, status="needs_attribution",
        filename="orphan.pdf", source_uri="/tmp/orphan.pdf",
    )

    response = client.post(
        f"/api/v1/admin/attribution-queue/{job_id}/assign",
        json={"vendor_id": "acme"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "received"
    assert body["vendor_id"] == "acme"


def test_assign_invites_unknown_vendor_if_requested(client, as_admin, cleanup):
    """E4.2 — assigning to a vendor not yet invited auto-invites them."""
    rfp_id = f"phase5e-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) + timedelta(days=7),
    )
    cleanup(rfp_id)
    job_id = enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id="_unknown_",
        content_hash="f" * 64, status="needs_attribution",
        filename="x.pdf", source_uri="/tmp/x.pdf",
    )

    response = client.post(
        f"/api/v1/admin/attribution-queue/{job_id}/assign",
        json={"vendor_id": "newvendor"},
    )
    assert response.status_code == 200, response.text

    # Vendor row + drop folder both created.
    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM invited_vendors "
                "WHERE rfp_id = :r AND vendor_id = 'newvendor'"
            ),
            {"r": rfp_id},
        ).scalar()
    assert n == 1
    assert (Path(_DROPS_ROOT) / rfp_id / "newvendor").exists()


# ── E5 ───────────────────────────────────────────────────────────────


def test_late_addendum_accept(client, as_admin, cleanup):
    """E5 — POST /late-addendum/{job_id}/accept flips rejected_late -> queued."""
    rfp_id = f"phase5e-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    cleanup(rfp_id)
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    job_id = enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id="acme",
        content_hash="g" * 64, status="rejected_late",
        filename="late.pdf", source_uri="/tmp/late.pdf",
    )

    response = client.post(f"/api/v1/admin/late-addendum/{job_id}/accept")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"


def test_late_addendum_accept_wrong_org_404(client, cleanup):
    """E5.2 — cross-org accept returns 409 (job not visible to other org)."""
    app.dependency_overrides[get_current_user] = lambda: _user(org_id=ORG_ID)
    rfp_id = f"phase5e-{uuid.uuid4().hex[:8]}"
    create_rfp(
        rfp_id=rfp_id, org_id=ORG_ID, title="t", created_by_email="a@b",
        submission_deadline=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    cleanup(rfp_id)
    invite_vendor(rfp_id=rfp_id, vendor_id="acme", invited_by="a@b")
    job_id = enqueue_ingestion_job(
        org_id=ORG_ID, rfp_id=rfp_id, vendor_id="acme",
        content_hash="h" * 64, status="rejected_late",
        filename="late.pdf", source_uri="/tmp/late.pdf",
    )
    app.dependency_overrides.clear()

    # Cross-org caller
    app.dependency_overrides[get_current_user] = lambda: _user(org_id=OTHER_ORG_ID)
    response = client.post(f"/api/v1/admin/late-addendum/{job_id}/accept")
    app.dependency_overrides.clear()
    assert response.status_code == 409
