"""
LIVE end-to-end test of the evaluation run path over HTTP.

This is the production path the UI runs — ``POST /start`` → ``POST /confirm`` →
``GET /results`` — driven through FastAPI's ``TestClient`` against the REAL agents,
LLM, and Qdrant. It complements the fast stubbed-graph seam test
(``test_run_pipeline_seam.py``, PR #283): that one proves the orchestration wires
up deterministically; THIS one proves the whole HTTP path produces a complete,
decided evaluation with the real model — the exact behaviour #281 restored.

It is expensive (real LLM, ~\$0.4, ~1–2 min) and needs the full local stack, so
it runs ONLY when explicitly opted in with ``RUN_LIVE_LLM=1`` + a real OpenAI key
AND the (git-ignored) sample PDFs are present. CI sets neither, so it is skipped
there — exactly like ``test_synthesis_verification_live.py``.

Limitation: like the rest of the functional suite, this runs under the RLS-exempt
OWNER engine (see tests/conftest.py), so it does NOT exercise RLS — that regression
is locked in separately by ``test_org_stamp_survives_rolled_back_txn`` (#281/#283).
Its value is the real HTTP → _run_pipeline → results path with live agents.

Run locally (stack up, BM25 cached):
    RUN_LIVE_LLM=1 PYTHONUTF8=1 python -m pytest \
        tests/integration/test_run_pipeline_live_e2e.py -q -s
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings

# ── Test documents (git-ignored; the same files the smoke test uses) ──────────
_DOCS = Path(__file__).resolve().parents[2] / "data" / "documents"
_RFP_PDF     = _DOCS / "RFP_IT_Managed_Services_MFS_2026.pdf"
_ACME_PDF    = _DOCS / "Acme_ClearPath_Proposal.pdf"
_APEX_PDF    = _DOCS / "nightbuilb_Apex_Technology_Proposal.pdf"
_CRITERIA    = _DOCS / "Vendor_Selection_Criteria_MFS.csv"

# ── Opt-in gate ───────────────────────────────────────────────────────────────
# Explicit RUN_LIVE_LLM (a key alone is not enough — CI injects a dummy key) AND
# the sample PDFs must exist (absent in CI, where data/documents is git-ignored).
pytestmark = pytest.mark.skipif(
    not (
        os.getenv("RUN_LIVE_LLM", "").lower() in ("1", "true", "yes")
        and settings.llm_provider == "openai"
        and settings.openai_api_key
        and _RFP_PDF.exists() and _ACME_PDF.exists() and _APEX_PDF.exists()
    ),
    reason="live e2e — set RUN_LIVE_LLM=1 with a real OPENAI_API_KEY and the "
           "data/documents/ sample PDFs present to run",
)

ORG_ID = "00000000-0000-0000-0000-000000000001"  # seeded dev org
_TERMINAL = {"complete", "blocked", "failed", "interrupted"}


@pytest.fixture
def client():
    """A bare app mounting only the evaluation router, with auth dependency-
    overridden to a dev-org company_admin (no JWT/login, no AuthMiddleware —
    /start stamps RLS explicitly and _run_pipeline sets its own org_context)."""
    from app.api.evaluation_routes import router
    from app.auth.dependencies import get_current_user
    from app.auth.jwt import TokenData

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: TokenData(
        email="e2e@meridian.test", org_id=ORG_ID, role="company_admin", dept_id=None)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def cleanup():
    """Best-effort DB teardown for the run created by the test."""
    ids: dict[str, str] = {}
    yield ids
    if not ids:
        return
    from app.db.fact_store import get_engine
    try:
        with get_engine().begin() as c:
            c.execute(sa.text("SET LOCAL app.current_org_id = :o"), {"o": ORG_ID})
            if ids.get("rfp_id"):
                c.execute(sa.text("DELETE FROM extracted_facts WHERE rfp_id = :r"), {"r": ids["rfp_id"]})
                c.execute(sa.text("DELETE FROM vendor_documents WHERE rfp_id = :r"), {"r": ids["rfp_id"]})
            if ids.get("setup_id"):
                c.execute(sa.text("DELETE FROM evaluation_setups WHERE setup_id = :s"), {"s": ids["setup_id"]})
            if ids.get("run_id"):
                c.execute(sa.text("DELETE FROM evaluation_runs WHERE run_id = CAST(:r AS uuid)"),
                          {"r": ids["run_id"]})
    except Exception:
        pass  # teardown is best-effort; a leftover local row is harmless


def test_live_http_run_path_completes(client, cleanup):
    """POST /start → POST /confirm → poll /results: the real HTTP path must drive
    the pipeline to 'complete' with both vendors decided and a recommendation."""
    files = [
        ("rfp_file",      (_RFP_PDF.name,  _RFP_PDF.read_bytes(),  "application/pdf")),
        ("vendor_files",  (_ACME_PDF.name, _ACME_PDF.read_bytes(), "application/pdf")),
        ("vendor_files",  (_APEX_PDF.name, _APEX_PDF.read_bytes(), "application/pdf")),
    ]
    if _CRITERIA.exists():
        files.append(("criteria_sheet", (_CRITERIA.name, _CRITERIA.read_bytes(), "text/csv")))
    data = {"rfp_title": f"E2E {uuid.uuid4().hex[:8]}", "department": "procurement",
            "contract_value": "500000", "currency": "GBP"}

    # 1) /start — also performs live criteria-extraction LLM work.
    r = client.post("/api/v1/evaluate/start", data=data, files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    cleanup.update(run_id=body["run_id"], setup_id=body.get("setup_id"),
                   rfp_id=body.get("rfp_id"))
    run_id = body["run_id"]

    # 2) /confirm — schedules _run_pipeline (the background task the UI triggers).
    rc = client.post(f"/api/v1/evaluate/{run_id}/confirm")
    assert rc.status_code == 200, rc.text

    # 3) Poll /results until terminal (robust to background-task timing).
    status, results = None, {}
    for _ in range(60):  # ~180s ceiling
        rr = client.get(f"/api/v1/evaluate/{run_id}/results")
        assert rr.status_code == 200, rr.text
        results = rr.json()
        status = results.get("status")
        if status in _TERMINAL:
            break
        time.sleep(3)

    # 4) The real HTTP path must produce a terminal, *decided* evaluation.
    #    A healthy run can legitimately end 'blocked' rather than 'complete' when
    #    the Critic HARD-escalates for human review (e.g. evidence coverage below
    #    the trust floor) — that is correct governance, not a failure. What proves
    #    the seam worked is that a FULL decision was produced (both vendors
    #    decided + a recommendation). The #281 crash-block, by contrast, ended
    #    'blocked' in 0.08s with NO decision and zero vendors — which these
    #    assertions would catch.
    assert status in ("complete", "blocked"), (
        f"run did not reach a terminal decision (status={status!r}) — "
        f"{results.get('decision')}")
    vendors = results.get("vendors") or []
    assert len(vendors) == 2, f"expected 2 vendors decided, got {len(vendors)}: {vendors}"
    assert all(v.get("decision") in ("shortlisted", "rejected") for v in vendors), \
        f"every vendor must be decided: {[(v.get('vendor_name'), v.get('decision')) for v in vendors]}"
    assert any(v.get("decision") == "shortlisted" for v in vendors), "no vendor shortlisted"
    assert (results.get("recommendation") or "").strip(), "no recommendation produced"
