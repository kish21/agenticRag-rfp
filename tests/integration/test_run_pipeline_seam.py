"""
Integration test for the FastAPI -> graph orchestration seam: `_run_pipeline`.

This is the path the UI actually runs (POST /confirm schedules `_run_pipeline`
as a background task) and the one the smoke test + benchmark do NOT exercise —
both drive `evaluation_graph.astream()` directly with a locally-built
`initial_state`, so they never touch `_run_pipeline`, its RLS-governed DB reads,
or its stream-merge loop. BOTH production bugs fixed in PR #281 lived in exactly
this seam:

  1. the RLS-governed run-load read returned zero rows ("Run not found in DB"), and
  2. langgraph 1.2.x `astream` "updates" mode yields ``{node: None}`` for a node
     whose return is empty/no-op (``planner_node`` returns ``{}``), and the merge
     ``{**final_state, **updated}`` raised ``TypeError: 'NoneType' object is not a
     mapping`` — blocking every run.

We stub the graph so the test stays fast and deterministic (no Qdrant / LLM)
while keeping `_run_pipeline`'s REAL DB reads, stream-merge loop, and decision
persist. This is the layer that broke; it is now covered.

The functional suite routes ``get_engine()`` to the RLS-exempt owner role (see
tests/conftest.py), so this file proves the seam wiring + the None-merge guard.
The RLS-specific regression for the same fix — that the tenant stamp survives a
rolled-back txn under the real ``platform_app`` role — lives in
tests/test_tenant_isolation_rls.py.
"""
import uuid

import sqlalchemy as sa

import app.api._evaluation.pipeline as pipeline_mod
from app.api._evaluation.pipeline import _run_pipeline
from app.db.fact_store import get_engine, save_evaluation_setup
from app.schemas.output_models import (
    EvaluationSetup, MandatoryCheck, ScoringCriterion, ExtractionTarget,
)

ORG_ID = "00000000-0000-0000-0000-000000000001"  # seeded dev org


class _FakeDecision:
    """Minimal stand-in for DecisionOutput — only the members `_run_pipeline`
    reads on the success path (model_dump + the *_vendors / approval_routing
    attrs). Avoids constructing the full nested decision schema."""
    shortlisted_vendors: list = []
    rejected_vendors: list = []
    approval_routing = None

    def model_dump(self, mode: str = "json") -> dict:
        return {"decision_id": "stub-decision",
                "shortlisted_vendors": [], "rejected_vendors": []}


def _fake_graph(diffs: list[dict]):
    """A stand-in compiled graph whose `astream` replays the given diffs — used
    to drive `_run_pipeline`'s merge loop with the exact ``{node: None}`` shape
    langgraph 1.2.x emits for empty-update nodes."""
    class _G:
        async def astream(self, initial_state, config=None):
            for d in diffs:
                yield d
    return _G()


def _seed_run(status: str = "running") -> str:
    """Insert a runnable evaluation_runs row + its EvaluationSetup. Returns run_id."""
    run_id   = str(uuid.uuid4())
    setup_id = f"setup-{run_id[:8]}"
    rfp_id   = f"rfp-{run_id[:8]}"
    setup = EvaluationSetup(
        setup_id=setup_id, org_id=ORG_ID, department="procurement", rfp_id=rfp_id,
        rfp_confirmed=True, confirmed_by="test", confirmed_at=None,
        source="manually_defined", total_weight=1.0,
        mandatory_checks=[MandatoryCheck(
            check_id="c1", name="check", description="d",
            what_passes="p", extraction_target_id="t1")],
        scoring_criteria=[ScoringCriterion(
            criterion_id="cr1", name="crit", weight=1.0,
            rubric_9_10="a", rubric_6_8="b", rubric_3_5="c", rubric_0_2="d",
            extraction_target_ids=["t1"])],
        extraction_targets=[ExtractionTarget(
            target_id="t1", name="target", description="d",
            fact_type="certification", is_mandatory=True, feeds_check_id="c1")],
    )
    save_evaluation_setup(setup.model_dump(mode="json"), org_id=ORG_ID)
    with get_engine().begin() as c:
        c.execute(sa.text("SET LOCAL app.current_org_id = :o"), {"o": ORG_ID})
        c.execute(sa.text("""
            INSERT INTO evaluation_runs
                (run_id, org_id, rfp_id, setup_id, rfp_title, department,
                 rfp_filename, rfp_bytes, status, vendor_ids, contract_value, currency)
            VALUES
                (CAST(:rid AS uuid), CAST(:o AS uuid), :rfp, :sid, 'seam test',
                 'procurement', 'rfp.pdf', :bytes, :status, ARRAY[]::text[], 0, 'GBP')
        """), {"rid": run_id, "o": ORG_ID, "rfp": rfp_id, "sid": setup_id,
               "bytes": b"%PDF-1.4 test", "status": status})
    return run_id


def _read_run(run_id: str):
    with get_engine().begin() as c:
        c.execute(sa.text("SET LOCAL app.current_org_id = :o"), {"o": ORG_ID})
        return c.execute(sa.text(
            "SELECT status, decision_output FROM evaluation_runs "
            "WHERE run_id = CAST(:r AS uuid)"), {"r": run_id}).fetchone()


async def test_run_pipeline_completes_through_the_seam(monkeypatch):
    """Happy path: the background `_run_pipeline` loads the run from the DB,
    streams the graph (including a ``{node: None}`` empty-update diff from the
    planner), persists the decision, and marks the run complete — the exact seam
    the smoke test / benchmark never run."""
    run_id = _seed_run(status="running")
    monkeypatch.setattr(pipeline_mod, "evaluation_graph", _fake_graph([
        {"planner": None},                                # langgraph empty-update -> the regression
        {"ingestion": None},
        {"decision": {"decision_output": _FakeDecision()}},
    ]))

    # Pre-fix this raised `TypeError: 'NoneType' object is not a mapping` on the
    # planner diff. Post-fix it must run clean to completion.
    await _run_pipeline(run_id, ORG_ID)

    row = _read_run(run_id)
    assert row is not None, "run row vanished — RLS/DB read regression"
    assert row[0] == "complete", f"expected status 'complete', got {row[0]!r}"
    assert row[1] is not None, "decision_output was not persisted through the seam"


async def test_run_pipeline_tolerates_all_none_diffs(monkeypatch):
    """Pure regression for the astream None-merge guard: a stream where EVERY
    node yields an empty (None) update must not crash the merge loop.

    NOTE: `_run_pipeline` catches its own exceptions and marks the run 'blocked',
    so a crash would NOT propagate here — we must assert on the END STATE. With
    no decision and no block, the success path drives the run to 'complete'; if
    the merge crashed on a None diff the run would be 'blocked' instead. So the
    'complete' assertion is what gives this test teeth."""
    run_id = _seed_run(status="running")
    monkeypatch.setattr(pipeline_mod, "evaluation_graph", _fake_graph([
        {"planner": None}, {"ingestion": None}, {"retrieval_done": None},
    ]))

    await _run_pipeline(run_id, ORG_ID)

    row = _read_run(run_id)
    assert row is not None and row[0] == "complete", (
        f"expected 'complete' (None diffs handled), got {row[0]!r} — "
        "a 'blocked' status means the None-merge guard regressed")
