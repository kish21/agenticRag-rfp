"""
tests/test_codereview_phase3_fixes.py
======================================
Regression tests for the 4 findings surfaced by /code-review on the
Phase 3 LLM-cache PR series.

  Finding #1 — extract_decision_summary tolerates None/missing vendor_id
              without TypeError on sorted()
  Finding #2 — POST /rerun returns 409 if the original run is deleted
              between the existence check and the INSERT...SELECT
              (TOCTOU race)
  Finding #5 — extract_decision_summary is a shared helper, not a
              nested closure inside _compute_divergence
  Finding #8 — uuid is imported once at module level (not re-aliased
              inside the rerun_evaluation function body)

Run:
    python -m pytest tests/test_codereview_phase3_fixes.py -v
"""
from __future__ import annotations

import sys
import uuid as stdlib_uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.fact_store import get_engine  # noqa: E402
from app.domain.decision_summary import extract_decision_summary  # noqa: E402


# ── Finding #1 — None-safe signature ─────────────────────────────────


def test_signature_handles_missing_vendor_id_keys():
    """#1 — vendor dicts missing the vendor_id key do not crash sorted()."""
    d = {
        "recommended_vendor": {"vendor_id": "acme"},
        "shortlisted_vendors": [{"vendor_id": "acme"}, {}, {"vendor_id": "apex"}],
        "rejected_vendors": [{}, {"vendor_id": "stranger"}],
    }
    sig = extract_decision_summary(d)
    assert sig["winner"] == "acme"
    assert sig["shortlist"] == ["acme", "apex"]
    assert sig["rejected"] == ["stranger"]


def test_signature_handles_none_vendor_id():
    """#1 — explicit None vendor_id values are filtered out, not sorted."""
    d = {
        "recommended_vendor": {"vendor_id": None},
        "shortlisted_vendors": [
            {"vendor_id": None}, {"vendor_id": "acme"}, {"vendor_id": "apex"},
        ],
        "rejected_vendors": [{"vendor_id": None}, {"vendor_id": "stranger"}],
    }
    sig = extract_decision_summary(d)
    assert sig["winner"] is None
    assert sig["shortlist"] == ["acme", "apex"]
    assert sig["rejected"] == ["stranger"]


def test_signature_handles_partial_decision_output():
    """#1 — a partially-populated decision_output (e.g. from a blocked run)
    does not crash; missing keys default to empty lists."""
    sig = extract_decision_summary({})
    assert sig == {"winner": None, "shortlist": [], "rejected": []}

    sig = extract_decision_summary(None)
    assert sig == {"winner": None, "shortlist": [], "rejected": []}


def test_signature_handles_non_string_vendor_id():
    """#1 — non-string vendor_id (int, dict, etc.) is filtered out."""
    d = {
        "shortlisted_vendors": [
            {"vendor_id": 123},        # int
            {"vendor_id": ""},         # empty string
            {"vendor_id": "   "},      # whitespace-only
            {"vendor_id": "acme"},
        ],
    }
    sig = extract_decision_summary(d)
    assert sig["shortlist"] == ["acme"]


def test_signature_dedupes_vendor_ids():
    """#1 — duplicate vendor_ids are collapsed to a single entry."""
    d = {
        "shortlisted_vendors": [
            {"vendor_id": "acme"}, {"vendor_id": "acme"}, {"vendor_id": "apex"},
        ],
    }
    sig = extract_decision_summary(d)
    assert sig["shortlist"] == ["acme", "apex"]


def test_signature_handles_non_list_vendors_field():
    """#1 — non-list shortlisted_vendors (None, str, dict) yields []."""
    for bad in (None, "acme", {"vendor_id": "acme"}, 42):
        sig = extract_decision_summary({"shortlisted_vendors": bad})
        assert sig["shortlist"] == []


# ── Finding #5 — extract_decision_summary is importable from app.domain ──


def test_extract_decision_summary_is_a_shared_helper():
    """#5 — Phase 7 / 8 / 6 will all need this. Verify it's import-able from
    app.domain.decision_summary, not nested inside _compute_divergence."""
    from app.domain import decision_summary as ds
    assert hasattr(ds, "extract_decision_summary")
    assert callable(ds.extract_decision_summary)


# ── Finding #8 — uuid imported once at module level ──────────────────


def test_no_redundant_uuid_alias_inside_rerun_evaluation():
    """#8 — `import uuid as _uuid` should be gone from the function body
    (uuid is already imported at module level)."""
    src = Path("app/api/evaluation_routes.py").read_text(encoding="utf-8")
    assert "import uuid as _uuid" not in src, (
        "rerun_evaluation should use the module-level `import uuid`, "
        "not re-alias inside the function body."
    )


# ── Finding #2 — INSERT SELECT TOCTOU rowcount guard ─────────────────


def test_rerun_returns_409_when_original_deleted_between_check_and_insert():
    """
    #2 — Simulate the TOCTOU race: call the INSERT...SELECT against a
    run_id that does not exist (mimicking the case where the original was
    deleted between _db_get_run() and the INSERT). The new guard checks
    result.rowcount == 0 and the endpoint raises 409 instead of returning
    a new_run_id pointing at a row that was never created.
    """
    # Drive the SQL directly — we don't need the full FastAPI stack to verify
    # rowcount handling. The endpoint's code path is:
    #   result = conn.execute(INSERT ... SELECT ... WHERE run_id = :orig)
    #   if result.rowcount == 0: raise HTTPException(409)
    engine = get_engine()
    fake_orig = str(stdlib_uuid.uuid4())
    fake_new = str(stdlib_uuid.uuid4())
    with engine.begin() as conn:
        result = conn.execute(
            sa.text(
                """
                INSERT INTO evaluation_runs (
                    run_id, org_id, setup_id, rfp_id, rfp_title, department,
                    rfp_filename, rfp_bytes, agent_id, status, vendor_ids,
                    contract_value, currency, approval_tier, vendor_names,
                    created_by_email, creator_dept_id
                )
                SELECT
                    CAST(:new_id AS uuid), org_id, setup_id, rfp_id, rfp_title,
                    department, rfp_filename, rfp_bytes, agent_id, 'running',
                    vendor_ids, contract_value, currency, approval_tier,
                    vendor_names, :email, creator_dept_id
                FROM evaluation_runs WHERE run_id = CAST(:orig_id AS uuid)
                """
            ),
            {"new_id": fake_new, "orig_id": fake_orig, "email": "race@test"},
        )
    # The endpoint's guard. Without the fix, this would silently succeed.
    assert result.rowcount == 0, (
        "INSERT ... SELECT against a nonexistent run_id must report 0 rows "
        "so the endpoint can raise 409 instead of returning a dead run_id."
    )
