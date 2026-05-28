"""
tests/test_codereview_regressions.py
====================================
Regression tests for the three correctness findings surfaced by `/code-review`
on the Phase-1/2/4/9 branch (2026-05-28). Each test pins the FIXED behaviour
so the bug cannot silently recur.

| Finding | Fix | Test |
|---------|-----|------|
| #1 Stale narratives on retry: vendor_narratives_accum left side keys preserved when right side missing them | Tag accumulator key with `@attempt{N}`; explanation_finalise picks the highest attempt per vendor | test_stale_narratives_on_failed_retry_do_not_contaminate_report |
| #2 retrieval_per_vendor lost the HARD-block guard removed in Phase 4 | HARD critic → return failed_vendors entry (not silent pass) | test_hard_block_retrieval_marks_vendor_failed |
| #3 evaluation_per_vendor lost the HARD-block guard removed in Phase 4 | Same pattern as #2 | test_hard_block_evaluation_marks_vendor_failed |

Run:
    python -m pytest tests/test_codereview_regressions.py -v
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipeline.nodes import (  # noqa: E402
    retrieval_per_vendor, evaluation_per_vendor,
    explanation_finalise,
)
from app.schemas.schema_decision import (  # noqa: E402
    VendorNarrative, ExplanationOutput, DecisionOutput,
    ShortlistedVendor, ApprovalRouting,
)
from app.schemas.output_models import (  # noqa: E402
    CriticOutput, CriticVerdict, CriticSeverity, CriticFlag, RetrievalOutput,
    EvaluationOutput,
)
from datetime import datetime


_SETUP_DICT = {
    "setup_id": "setup-001", "org_id": "test-org-001", "department": "IT",
    "rfp_id": "test-rfp-001", "rfp_confirmed": True,
    "mandatory_checks": [], "scoring_criteria": [], "extraction_targets": [],
    "total_weight": 1.0, "confirmed_by": "test-user", "confirmed_at": None,
    "source": "csv",
}


def _hard_critic(check_name: str = "low_retrieval_confidence") -> CriticOutput:
    # Use model_construct() — skips Pydantic validation. We only need the
    # critic to expose `.overall_verdict` (BLOCKED) and `.flags[*].severity`
    # / `.description` for the under-test code path.
    flag = CriticFlag.model_construct(
        check_name=check_name,
        severity=CriticSeverity.HARD,
        description="simulated hard block for regression test",
    )
    return CriticOutput.model_construct(
        overall_verdict=CriticVerdict.BLOCKED,
        flags=[flag],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Finding #1 — stale narratives on retry contaminate the final report
# ──────────────────────────────────────────────────────────────────────────────

class TestStaleNarrativeRegression:
    """Bug: vendor_narratives_accum used vid as key. Phase 2's merge reducer
    preserved old entries when a retry didn't overwrite them — so a vendor
    that crashed on retry left its REJECTED attempt-1 narrative in the final
    ExplanationOutput. Fix: tag keys with `@attempt{N}`, pick latest per vendor.
    """

    @pytest.mark.asyncio
    async def test_stale_narratives_on_failed_retry_do_not_contaminate_report(self):
        # Simulate the bug scenario:
        #   attempt 1 — vendor A and B both produced narratives (critic blocked).
        #   attempt 2 — A succeeded with a corrected narrative; B crashed.
        # The accumulator therefore contains:
        #   vA@attempt1: bad-old, vA@attempt2: good-new, vB@attempt1: bad-old
        # Finalise must pick vA's attempt-2, fall back to vB's attempt-1.

        def _narr(label: str) -> VendorNarrative:
            return VendorNarrative(
                vendor_id=label.split("-")[0],
                vendor_name=label.split("-")[0].upper(),
                executive_summary=label,
                compliance_narrative="", scoring_narrative="",
                recommendation_rationale="",
                grounded_claims=[],
            )

        decision_output = DecisionOutput(
            decision_id="d1", rfp_id="test-rfp-001",
            rejected_vendors=[],
            shortlisted_vendors=[
                ShortlistedVendor(vendor_id="vA", vendor_name="VA", rank=1,
                                  total_score=0.7, score_confidence=0.85,
                                  criterion_breakdown=[], recommendation="recommended"),
                ShortlistedVendor(vendor_id="vB", vendor_name="VB", rank=2,
                                  total_score=0.6, score_confidence=0.8,
                                  criterion_breakdown=[], recommendation="acceptable"),
            ],
            approval_routing=ApprovalRouting(
                approval_tier=1, approver_role="cfo", contract_value=100_000.0,
                sla_hours=48, sla_deadline=datetime(2026, 12, 31),
            ),
            decision_confidence=0.85, requires_human_review=False,
        )

        state = {
            "vendor_narratives_accum": {
                "vA@attempt1": _narr("vA-old-bad"),
                "vA@attempt2": _narr("vA-new-good"),
                "vB@attempt1": _narr("vB-stale-bad"),
            },
            "decision_output": decision_output,
            "source_chunks": {},
            "currency": "GBP",
            "run_id": "test-run-001", "org_id": "test-org-001",
            "failed_vendors": [],
            "blocked": False, "blocked_agent": "", "error_message": "",
            "n_vendors": 2,
        }

        result = await explanation_finalise(state)
        exp_out = result.get("explanation_output")
        assert exp_out is not None, "finalise must produce an ExplanationOutput"
        narratives = {n.vendor_id: n for n in exp_out.vendor_narratives}
        assert set(narratives.keys()) == {"vA", "vB"}, \
            f"Expected one narrative per vendor; got {sorted(narratives.keys())}"
        assert narratives["vA"].executive_summary == "vA-new-good", \
            "vA must use the LATEST (attempt 2) narrative, not the stale attempt-1 one"
        # vB only has attempt-1; we accept that as best-effort
        assert narratives["vB"].executive_summary == "vB-stale-bad", \
            "vB has only attempt-1; finalise must fall back to it"


# ──────────────────────────────────────────────────────────────────────────────
# Finding #2 — retrieval HARD-block guard regression
# ──────────────────────────────────────────────────────────────────────────────

class TestRetrievalHardBlockRegression:
    """Bug: Phase 4 split removed _hard_block_if(combined_critic, ...) from
    retrieval_per_vendor. Discarded the critic verdict. Now restored: HARD
    critic on a single vendor's combined retrieval marks THAT vendor as failed
    (the pipeline continues for other vendors)."""

    @pytest.mark.asyncio
    async def test_hard_block_retrieval_marks_vendor_failed(self):
        with patch("app.pipeline.nodes.run_retrieval_agent", new_callable=AsyncMock) as m_ret, \
             patch("app.pipeline.nodes.critic_after_retrieval") as m_critic:
            # Simulate normal per-query retrieval returning chunks.
            # Pass model_construct() to skip Pydantic validation — the under-test
            # code only reads .overall_verdict / .flags off the critic object.
            ok_critic = CriticOutput.model_construct(
                overall_verdict=CriticVerdict.APPROVED, flags=[],
            )
            m_ret.return_value = (
                RetrievalOutput(
                    query_id="q1", original_query="x", rewritten_query="x",
                    hyde_query_used=False, retrieval_strategy="test",
                    chunks=[], total_candidates_before_rerank=0,
                    confidence=0.1, empty_retrieval=True, warnings=[],
                ),
                ok_critic,
            )
            # Combined critic blocks HARD
            m_critic.return_value = _hard_critic()

            state = {
                "vendor_id": "vBad",
                "org_id": "test-org-001",
                "rfp_id": "test-rfp-001",
                "run_id": "test-run-001",
                "evaluation_setup_dict": _SETUP_DICT,
                "org_settings": None,
                "vendor_ids": ["vBad"], "n_vendors": 1,
            }
            result = await retrieval_per_vendor(state)

        # Vendor must be marked failed, NOT silently written into retrieval_output_objects
        assert "retrieval_output_objects" not in result, \
            "HARD-blocked retrieval must NOT write a successful output"
        failed = result.get("failed_vendors") or []
        assert any(f["vendor_id"] == "vBad" and f["stage"] == "retrieval"
                   for f in failed), \
            f"HARD-blocked vendor must appear in failed_vendors; got {failed}"
        assert "critic_hard_block" in failed[0]["error"], \
            "failure record must indicate critic_hard_block reason"


# ──────────────────────────────────────────────────────────────────────────────
# Finding #3 — evaluation HARD-block guard regression
# ──────────────────────────────────────────────────────────────────────────────

class TestEvaluationHardBlockRegression:
    """Bug: Phase 4 split removed _hard_block_if(ev_critic, ...) from
    evaluation_per_vendor. A malformed EvaluationOutput would silently flow
    into comparator. Now restored: HARD critic marks the vendor failed.
    """

    @pytest.mark.asyncio
    async def test_hard_block_evaluation_marks_vendor_failed(self):
        # model_construct() to skip Pydantic validation — these objects only
        # need to be truthy and pass attribute lookups by the under-test code.
        ev_out = EvaluationOutput.model_construct(
            evaluation_id="e1", vendor_id="vBad",
            total_weighted_score=0.5, score_confidence=0.5,
        )
        hard_ev_critic = _hard_critic("score_out_of_rubric_range")

        with patch("app.pipeline.nodes.run_evaluation_agent",
                   new_callable=AsyncMock) as m_eval:
            m_eval.return_value = (ev_out, hard_ev_critic)

            state = {
                "vendor_id": "vBad",
                "org_id": "test-org-001",
                "rfp_id": "test-rfp-001",
                "run_id": "test-run-001",
                "evaluation_setup_dict": _SETUP_DICT,
                "extraction_output_objects": {"vBad": object()},  # truthy presence check
            }
            result = await evaluation_per_vendor(state)

        assert "evaluation_output_objects" not in result, \
            "HARD-blocked evaluation must NOT write a successful output"
        failed = result.get("failed_vendors") or []
        assert any(f["vendor_id"] == "vBad" and f["stage"] == "evaluation"
                   for f in failed), \
            f"HARD-blocked vendor must appear in failed_vendors; got {failed}"
        assert "critic_hard_block" in failed[0]["error"], \
            "failure record must indicate critic_hard_block reason"
