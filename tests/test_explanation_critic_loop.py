"""
tests/test_explanation_critic_loop.py
=====================================
Phase 2 exit-criterion tests — verifies the critic-as-controller retry loop.

The Explanation stage in Phase 2 is no longer "succeed or hard-block." When
the critic flags low grounding it can now route back to explanation_start
with structured feedback for up to 2 retries (3 total attempts). These tests
mock the per-vendor explanation work so we can deterministically force each
of the four routing outcomes:

  1. HAPPY        — critic approves on the first try → END
  2. RETRY        — critic blocks once, retry succeeds → END after 1 retry
  3. EXHAUSTED    — critic blocks all 3 attempts → blocked sentinel + END
  4. FEEDBACK     — the second attempt sees the critic's feedback in state

Tests bypass real LLM/Qdrant by patching nodes inside graph.py. Each test
counts how many times explanation_per_vendor is invoked to prove the
retry loop fired the right number of times.

Run:
    python -m pytest tests/test_explanation_critic_loop.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipeline.graph import build_graph  # noqa: E402
from app.schemas.schema_decision import (  # noqa: E402
    ExplanationOutput, VendorNarrative, DecisionOutput, RejectionNotice,
    ShortlistedVendor, ApprovalRouting,
)
from app.schemas.output_models import (  # noqa: E402
    CriticOutput, CriticVerdict, CriticSeverity, CriticFlag,
)
from datetime import datetime


_NODE_PATCH_NAMES = [
    "planner_node", "ingestion_node",
    "retrieval_start", "retrieval_per_vendor", "retrieval_done",
    "extraction_start", "extraction_per_vendor", "extraction_done",
    "evaluation_start", "evaluation_per_vendor", "evaluation_done",
    "comparator_node", "decision_node",
    "explanation_start", "explanation_per_vendor", "explanation_finalise",
    "explanation_critic",
]

_SETUP_DICT = {
    "setup_id": "setup-001", "org_id": "test-org-001", "department": "IT",
    "rfp_id": "test-rfp-001", "rfp_confirmed": True,
    "mandatory_checks": [], "scoring_criteria": [], "extraction_targets": [],
    "total_weight": 1.0, "confirmed_by": "test-user", "confirmed_at": None,
    "source": "csv",
}


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


def _base_state(grounding_completeness: float = 1.0) -> dict:
    """Initial state including a pre-built ExplanationOutput so the critic
    can run against it. Tests mock around this so explanation_finalise is
    a no-op pass-through."""
    decision_output = DecisionOutput(
        decision_id="dec-1", rfp_id="test-rfp-001",
        rejected_vendors=[],
        shortlisted_vendors=[ShortlistedVendor(
            vendor_id="v1", vendor_name="V1", rank=1, total_score=0.8,
            score_confidence=0.9, criterion_breakdown=[],
            recommendation="recommended",
        )],
        approval_routing=ApprovalRouting(
            approval_tier=1, approver_role="cfo", contract_value=100_000.0,
            sla_hours=48, sla_deadline=datetime(2026, 12, 31),
        ),
        decision_confidence=0.85, requires_human_review=False,
    )
    exp_out = ExplanationOutput(
        explanation_id="exp-1",
        executive_summary="test", methodology_note="test",
        limitations=[], grounding_completeness=grounding_completeness,
        report_confidence=0.9,
        vendor_narratives=[VendorNarrative(
            vendor_id="v1", vendor_name="V1",
            executive_summary="", compliance_narrative="",
            scoring_narrative="", recommendation_rationale="",
            grounded_claims=[],
        )],
    )
    return {
        "run_id": "test-run-001", "org_id": "test-org-001",
        "rfp_id": "test-rfp-001", "rfp_title": "Test RFP",
        "rfp_filename": "rfp.pdf", "rfp_bytes": b"",
        "vendor_ids": ["v1"], "contract_value": 100_000.0, "currency": "GBP",
        "setup_id": "setup-001", "n_vendors": 1,
        "evaluation_setup_dict": _SETUP_DICT,
        "vendor_file_map": {"v1": (b"", "v1.pdf")},
        "org_settings": None, "vendor_id": "",
        "retrieval_output_objects": {}, "extraction_output_objects": {},
        "evaluation_output_objects": {}, "source_chunks": {},
        "vendor_narratives_accum": {}, "failed_vendors": [],
        "comparator_output": None,
        "decision_output": decision_output,
        "explanation_output": exp_out,
        "explanation_retry_count": 0,
        "explanation_critic_feedback": "",
        "explanation_retry_requested": False,
        "blocked": False, "blocked_agent": "", "error_message": "",
    }


def _block_critic_mock(attempts_before_success: int):
    """Mock for explanation_critic that blocks for N attempts then approves.

    attempts_before_success=2 means: block on attempt 1, block on attempt 2,
    approve on attempt 3 (the third try succeeds).
    attempts_before_success=99 means: always block (exhausts the budget).

    Mirrors the production critic's return-shape contract — sets
    `explanation_retry_requested` flag explicitly on retry/approve."""
    async def node(state):
        attempt = (state.get("explanation_retry_count") or 0)
        if attempt < attempts_before_success:
            if attempt >= 2:
                # 2 retries already consumed = exhausted (3rd attempt blocked)
                return {
                    "blocked": True,
                    "blocked_agent": "explanation",
                    "error_message": f"[CRITIC BLOCK after {attempt + 1} attempts] simulated",
                    "explanation_retry_requested": False,
                }
            # Request retry
            return {
                "explanation_retry_count": attempt + 1,
                "explanation_critic_feedback": f"attempt-{attempt + 1}-feedback",
                "explanation_output": None,
                "explanation_retry_requested": True,
            }
        # Approve
        return {"explanation_retry_requested": False}
    node.__name__ = "explanation_critic"
    return node


def _approve_critic_mock():
    """Overrides the module-level definition to match the new contract."""
    async def node(state):
        return {"explanation_retry_requested": False}
    node.__name__ = "explanation_critic"
    return node


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestExplanationCriticLoop:

    @pytest.mark.asyncio
    async def test_happy_path_approves_on_first_attempt(self):
        """Critic approves immediately → no retry, run reaches END."""
        per_vendor_calls = 0

        async def counting_per_vendor(state):
            nonlocal per_vendor_calls
            per_vendor_calls += 1
            return {"vendor_narratives_accum": {state["vendor_id"]: "narrative-ok"}}

        overrides = {
            "explanation_per_vendor": counting_per_vendor,
            "explanation_critic": _approve_critic_mock(),
        }
        with _patch_all(overrides):
            graph = build_graph()
            final = await graph.ainvoke(
                _base_state(grounding_completeness=1.0),
                {"recursion_limit": 50},
            )

        assert per_vendor_calls == 1, \
            f"Happy path: explanation_per_vendor should fire ONCE; got {per_vendor_calls}"
        assert final["blocked"] is False
        assert (final.get("explanation_retry_count") or 0) == 0

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_attempt_2(self):
        """Critic blocks once, then approves on the retry → explanation_per_vendor
        fires twice, retry_count=1 on success, no block."""
        per_vendor_calls = 0

        async def counting_per_vendor(state):
            nonlocal per_vendor_calls
            per_vendor_calls += 1
            return {"vendor_narratives_accum": {state["vendor_id"]: f"narrative-{per_vendor_calls}"}}

        overrides = {
            "explanation_per_vendor": counting_per_vendor,
            "explanation_critic": _block_critic_mock(attempts_before_success=1),
        }
        with _patch_all(overrides):
            graph = build_graph()
            final = await graph.ainvoke(
                _base_state(), {"recursion_limit": 50},
            )

        assert per_vendor_calls == 2, \
            f"Retry path: explanation_per_vendor should fire TWICE; got {per_vendor_calls}"
        assert final["blocked"] is False, \
            "After a successful retry, the run should NOT be blocked"
        assert final.get("explanation_retry_count") == 1, \
            f"retry_count should be 1 after one retry; got {final.get('explanation_retry_count')}"

    @pytest.mark.asyncio
    async def test_exhausted_after_3_attempts(self):
        """Critic blocks all 3 attempts → blocked sentinel, run reaches END."""
        per_vendor_calls = 0

        async def counting_per_vendor(state):
            nonlocal per_vendor_calls
            per_vendor_calls += 1
            return {"vendor_narratives_accum": {state["vendor_id"]: f"narrative-{per_vendor_calls}"}}

        overrides = {
            "explanation_per_vendor": counting_per_vendor,
            "explanation_critic": _block_critic_mock(attempts_before_success=99),
        }
        with _patch_all(overrides):
            graph = build_graph()
            final = await graph.ainvoke(
                _base_state(), {"recursion_limit": 50},
            )

        assert per_vendor_calls == 3, \
            f"Exhausted path: explanation_per_vendor should fire 3 times (1 + 2 retries); got {per_vendor_calls}"
        assert final["blocked"] is True
        assert final["blocked_agent"] == "explanation"
        assert "after 3 attempts" in final["error_message"].lower() \
               or "CRITIC BLOCK" in final["error_message"]

    @pytest.mark.asyncio
    async def test_feedback_propagates_to_next_attempt(self):
        """The structured feedback the critic produces on attempt N must be
        visible to explanation_per_vendor on attempt N+1 (via state)."""
        feedback_seen_per_attempt: list[str] = []

        async def feedback_aware_per_vendor(state):
            feedback_seen_per_attempt.append(
                state.get("explanation_critic_feedback") or ""
            )
            return {"vendor_narratives_accum": {state["vendor_id"]: "narrative-ok"}}

        # Block once → retry → approve on attempt 2
        overrides = {
            "explanation_per_vendor": feedback_aware_per_vendor,
            "explanation_critic": _block_critic_mock(attempts_before_success=1),
        }
        with _patch_all(overrides):
            graph = build_graph()
            await graph.ainvoke(_base_state(), {"recursion_limit": 50})

        # Attempt 1 saw empty feedback (first try, no prior critic input).
        # Attempt 2 saw the feedback the critic produced on attempt 1.
        assert len(feedback_seen_per_attempt) == 2, \
            f"Expected 2 attempts; observed {len(feedback_seen_per_attempt)}"
        assert feedback_seen_per_attempt[0] == "", \
            "First attempt should see empty feedback (no prior critic verdict)"
        assert feedback_seen_per_attempt[1] != "", \
            "Second attempt MUST see non-empty feedback from the critic"
        assert "attempt-1-feedback" in feedback_seen_per_attempt[1], \
            f"Second attempt should see the critic's structured feedback; " \
            f"got {feedback_seen_per_attempt[1]!r}"


# ── Direct unit test of the critic node's feedback builder ────────────────────

class TestFeedbackBuilder:
    """Verifies the feedback-string content directly, independent of the graph."""

    def test_feedback_includes_grounding_pct_and_diagnostics(self):
        from app.pipeline.nodes import _build_critic_feedback

        narrative = VendorNarrative(
            vendor_id="v1", vendor_name="V1",
            executive_summary="", compliance_narrative="",
            scoring_narrative="", recommendation_rationale="",
            grounded_claims=[],
            ungrounded_examples=[
                {"claim_text": "Vendor scored 7.5/10",
                 "llm_grounding_quote": "Score: 7.5/10",
                 "cited_chunk_id": "fake-chunk",
                 "chunk_exists": False,
                 "source_excerpt": "(no chunk)",
                 "diagnosis_hint": "wrong_chunk_id"},
            ],
        )
        exp_out = ExplanationOutput(
            explanation_id="e1", executive_summary="", vendor_narratives=[narrative],
            methodology_note="", limitations=[],
            grounding_completeness=0.33, report_confidence=0.85,
        )
        # _build_critic_feedback only reads exp_out fields, not exp_critic — we
        # pass None to confirm that contract (and avoid constructing a complex
        # CriticOutput fixture for an unused argument).
        feedback = _build_critic_feedback(exp_out, None)
        assert "33%" in feedback, "Feedback must surface the grounding percentage"
        assert "Vendor scored 7.5/10" in feedback, \
            "Feedback must include concrete ungrounded-claim examples"
        assert "system_facts" in feedback, \
            "Feedback must remind the LLM about the system_facts category"
        assert "wrong_chunk_id" in feedback, \
            "Feedback must include the diagnosis hint so the model knows the failure type"
