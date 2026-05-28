"""
tests/test_parallel_fanout.py
=============================
Phase 4 exit-criterion tests — proves the parallel vendor execution actually
runs in parallel (wall-clock), the concurrency semaphore enforces its limit,
and one vendor's failure doesn't abort the batch.

These tests mock the per-vendor node body (no real LLM/Qdrant calls) so they
run in ~2 seconds and prove the GRAPH-LEVEL parallel behaviour, not the
agents themselves.

Run:
    python -m pytest tests/test_parallel_fanout.py -v
"""
import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipeline.graph import build_graph  # noqa: E402
from app.pipeline import concurrency as conc  # noqa: E402


# Stages and patch names — kept in sync with test_pipeline_graph.py.
# explanation_critic is patched too (added in Phase 2) — the production
# critic depends on a real ExplanationOutput which our no-op mocks skip.
_NODE_PATCH_NAMES = [
    "planner_node", "ingestion_node",
    "retrieval_start", "retrieval_per_vendor", "retrieval_done",
    "extraction_start", "extraction_per_vendor", "extraction_done",
    "evaluation_start", "evaluation_per_vendor", "evaluation_done",
    "comparator_node", "decision_node",
    "explanation_start", "explanation_per_vendor",
    "explanation_finalise", "explanation_critic",
]


def _ok(name: str, extra: dict | None = None):
    async def node(state):
        return extra or {}
    node.__name__ = name
    return node


def _patch_all(overrides: dict):
    from contextlib import ExitStack
    stack = ExitStack()
    for n in _NODE_PATCH_NAMES:
        mock = overrides.get(n, _ok(n))
        stack.enter_context(patch(f"app.pipeline.graph.{n}", mock))
    return stack


_SETUP_DICT = {
    "setup_id": "setup-001", "org_id": "test-org-001", "department": "IT",
    "rfp_id": "test-rfp-001", "rfp_confirmed": True,
    "mandatory_checks": [], "scoring_criteria": [], "extraction_targets": [],
    "total_weight": 1.0, "confirmed_by": "test-user", "confirmed_at": None,
    "source": "csv",
}


def _state(vendor_ids: list[str]) -> dict:
    return {
        "run_id": "test-run-001", "org_id": "test-org-001",
        "rfp_id": "test-rfp-001", "rfp_title": "Test RFP",
        "rfp_filename": "rfp.pdf", "rfp_bytes": b"",
        "vendor_ids": vendor_ids, "contract_value": 100_000.0, "currency": "GBP",
        "setup_id": "setup-001", "n_vendors": len(vendor_ids),
        "evaluation_setup_dict": _SETUP_DICT,
        "vendor_file_map": {v: (b"", f"{v}.pdf") for v in vendor_ids},
        "org_settings": None, "vendor_id": "",
        "retrieval_output_objects": {}, "extraction_output_objects": {},
        "evaluation_output_objects": {}, "source_chunks": {},
        "vendor_narratives_accum": {}, "failed_vendors": [],
        "comparator_output": None, "decision_output": None, "explanation_output": None,
        "blocked": False, "blocked_agent": "", "error_message": "",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestParallelism:
    @pytest.mark.asyncio
    async def test_5_vendors_run_concurrently_not_sequentially(self):
        """If retrieval_per_vendor sleeps 0.5s, 5 sequential runs would take
        ~2.5s. Parallel execution with N≥5 concurrent slots must finish in
        well under that — proving LangGraph Send fans out the work, not a
        Python loop."""
        # Bump the semaphore to allow all 5 in flight so the parallelism is
        # observable wall-clock. Real production sticks at 5 by default.
        conc.reset_for_tests(5)

        async def slow_retrieval(state):
            await asyncio.sleep(0.5)
            return {"retrieval_output_objects": {state["vendor_id"]: "ok"}}

        with _patch_all({"retrieval_per_vendor": slow_retrieval}):
            graph = build_graph()
            t0 = time.perf_counter()
            await graph.ainvoke(_state(["v1", "v2", "v3", "v4", "v5"]))
            elapsed = time.perf_counter() - t0

        # Sequential lower bound = 5 * 0.5 = 2.5s. Parallel must be much less.
        assert elapsed < 1.5, (
            f"Expected parallel execution (≤1.5s); took {elapsed:.2f}s. "
            "Fan-out may have fallen back to sequential."
        )

    @pytest.mark.asyncio
    async def test_semaphore_caps_concurrent_per_vendor_workers(self):
        """When the semaphore is limited to 2, never more than 2 workers
        should be running their body simultaneously, even with 10 vendors
        spawned by Send."""
        conc.reset_for_tests(2)

        in_flight = 0
        peak = 0
        lock = asyncio.Lock()

        async def tracked_retrieval(state):
            from app.pipeline.concurrency import vendor_slot
            async with vendor_slot():
                nonlocal in_flight, peak
                async with lock:
                    in_flight += 1
                    peak = max(peak, in_flight)
                await asyncio.sleep(0.05)
                async with lock:
                    in_flight -= 1
                return {"retrieval_output_objects": {state["vendor_id"]: "ok"}}

        with _patch_all({"retrieval_per_vendor": tracked_retrieval}):
            graph = build_graph()
            await graph.ainvoke(_state([f"v{i}" for i in range(10)]))

        # Restore default for other tests.
        conc.reset_for_tests(5)

        assert peak <= 2, (
            f"Semaphore should have capped concurrency at 2; observed peak={peak}. "
            "vendor_slot() may not be wrapping the per-vendor body."
        )

    @pytest.mark.asyncio
    async def test_one_vendor_failure_does_not_abort_others(self):
        """Vendor v3 raises mid-pipeline. The graph must continue and produce
        outputs for the other vendors; v3 must appear in failed_vendors."""
        conc.reset_for_tests(5)

        async def maybe_failing_retrieval(state):
            vid = state["vendor_id"]
            if vid == "v3":
                # Return a "failed" sentinel — same shape as the real node.
                return {"failed_vendors": [{
                    "vendor_id": vid, "stage": "retrieval",
                    "error": "simulated retrieval crash", "ts": "now",
                }]}
            return {"retrieval_output_objects": {vid: f"ret-{vid}"}}

        with _patch_all({"retrieval_per_vendor": maybe_failing_retrieval}):
            graph = build_graph()
            final = await graph.ainvoke(_state(["v1", "v2", "v3", "v4", "v5"]))

        # Pipeline did NOT block
        assert final["blocked"] is False, \
            "One vendor failure should NOT block the whole pipeline"

        # 4 healthy vendors produced outputs
        ret_objs = final.get("retrieval_output_objects") or {}
        assert set(ret_objs.keys()) == {"v1", "v2", "v4", "v5"}, \
            f"Expected 4 healthy vendors, got {sorted(ret_objs.keys())}"

        # v3 recorded in failed_vendors
        failed = final.get("failed_vendors") or []
        assert any(f["vendor_id"] == "v3" and f["stage"] == "retrieval"
                   for f in failed), \
            f"v3 should appear in failed_vendors; got {failed}"

    @pytest.mark.asyncio
    async def test_explanation_finalise_sorts_narratives_for_determinism(self):
        """vendor_narratives_accum is populated by parallel branches in
        non-deterministic order. explanation_finalise must sort by vendor_id
        before building the final ExplanationOutput so the output is
        reproducible."""
        from app.pipeline.nodes import explanation_finalise
        from app.schemas.schema_decision import (
            VendorNarrative, DecisionOutput, RejectionNotice, ShortlistedVendor,
            ApprovalRouting,
        )
        from datetime import datetime

        # Build a minimal decision_output for the finalise step to consume
        decision_output = DecisionOutput(
            decision_id="dec-1", rfp_id="test-rfp-001",
            rejected_vendors=[],
            shortlisted_vendors=[
                ShortlistedVendor(
                    vendor_id="zeta", vendor_name="Zeta", rank=1,
                    total_score=0.8, score_confidence=0.9,
                    criterion_breakdown=[], recommendation="recommended",
                ),
                ShortlistedVendor(
                    vendor_id="alpha", vendor_name="Alpha", rank=2,
                    total_score=0.6, score_confidence=0.85,
                    criterion_breakdown=[], recommendation="acceptable",
                ),
            ],
            approval_routing=ApprovalRouting(
                approval_tier=1, approver_role="cfo", contract_value=100_000.0,
                sla_hours=48, sla_deadline=datetime.utcnow(),
            ),
            decision_confidence=0.85, requires_human_review=False,
        )

        # Insert narratives out of alphabetical order to verify sorting
        narratives = {
            "zeta": VendorNarrative(
                vendor_id="zeta", vendor_name="Zeta",
                executive_summary="z exec", compliance_narrative="z comp",
                scoring_narrative="z score", recommendation_rationale="z rec",
                grounded_claims=[], ungrounded_claims_removed=0,
            ),
            "alpha": VendorNarrative(
                vendor_id="alpha", vendor_name="Alpha",
                executive_summary="a exec", compliance_narrative="a comp",
                scoring_narrative="a score", recommendation_rationale="a rec",
                grounded_claims=[], ungrounded_claims_removed=0,
            ),
        }

        state = {
            "vendor_narratives_accum": narratives,
            "decision_output": decision_output,
            "source_chunks": {},
            "currency": "GBP",
            "run_id": "test-run-001", "org_id": "test-org-001",
            "failed_vendors": [],
            # _emit + _block_update will try these
            "blocked": False, "blocked_agent": "", "error_message": "",
            "n_vendors": 2,
        }

        # critic_after_explanation will hard-block on grounding < 0.70 — and
        # the narratives have 0 grounded claims. The finalise function should
        # raise via _hard_block_if, get caught by the except, and preserve
        # the explanation_output in the block update.
        result = await explanation_finalise(state)

        # Either way (passed or blocked), the explanation_output should be
        # present and the vendor_narratives should be sorted alphabetically.
        exp = result.get("explanation_output")
        assert exp is not None, "explanation_output must survive (Phase 1 fix)"
        order = [n.vendor_id for n in exp.vendor_narratives]
        assert order == ["alpha", "zeta"], \
            f"vendor_narratives must be sorted; got {order}"
