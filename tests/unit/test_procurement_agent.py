"""
Full procurement evaluation pipeline test.
Validates Evaluation Agent + Comparator Agent without real LLM or DB calls.
"""
import asyncio
import json
import os
import sys
import uuid

# Ensure project root is on sys.path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.output_models import (
    ComplianceStatus,
    ComparatorOutput,
    CriterionScore,
    DecisionBasis,
    EvaluationOutput,
    EvaluationSetup,
    ExtractionTarget,
    MandatoryCheck,
    ScoringCriterion,
)


# ── Test fixtures ──────────────────────────────────────────────────────────────

def make_evaluation_setup(has_mandatory_checks: bool = True) -> EvaluationSetup:
    targets = [
        ExtractionTarget(
            target_id="target-cert",
            name="Security Certification",
            description="Vendor security certification status",
            fact_type="certification",
            is_mandatory=True,
            feeds_check_id="check-cert" if has_mandatory_checks else None,
        ),
        ExtractionTarget(
            target_id="target-sla",
            name="SLA Commitments",
            description="Service level commitments",
            fact_type="sla",
            is_mandatory=False,
            feeds_criterion_id="crit-sla",
        ),
    ]
    mandatory_checks = (
        [
            MandatoryCheck(
                check_id="check-cert",
                name="Security Certification Required",
                description="Vendor must hold a current security certification",
                what_passes="Vendor holds a current, valid security certification from an accredited body",
                extraction_target_id="target-cert",
            )
        ]
        if has_mandatory_checks
        else []
    )
    scoring_criteria = [
        ScoringCriterion(
            criterion_id="crit-sla",
            name="SLA Quality",
            weight=1.0,
            rubric_9_10="Response under 30 min, uptime 99.9%+",
            rubric_6_8="Response under 2 hours, uptime 99.5%+",
            rubric_3_5="Response under 8 hours, uptime 99%+",
            rubric_0_2="No SLA commitments or poor metrics",
            extraction_target_ids=["target-sla"],
        )
    ]
    return EvaluationSetup(
        setup_id=str(uuid.uuid4()),
        org_id="org-test",
        department="procurement",
        rfp_id="rfp-test",
        rfp_confirmed=True,
        mandatory_checks=mandatory_checks,
        scoring_criteria=scoring_criteria,
        extraction_targets=targets,
        total_weight=1.0,
        confirmed_by="test-user",
        confirmed_at=datetime.utcnow(),
        source="manually_defined",
    )


MOCK_FACTS = {
    "certifications": [
        {
            "standard_name": "Security Certification",
            "status": "current",
            "confidence": 0.9,
            "grounding_quote": "We hold a current accredited security certification.",
            "source_chunk_id": "chunk-1",
        }
    ],
    "insurance": [],
    "slas": [
        {
            "priority_level": "P1",
            "response_minutes": 30,
            "uptime_percentage": 99.9,
            "confidence": 0.85,
            "grounding_quote": "P1 response within 30 minutes, 99.9% uptime guaranteed.",
            "source_chunk_id": "chunk-2",
        }
    ],
    "projects": [],
    "pricing": [],
    "extracted_facts": [],
}

MOCK_FACTS_NO_CERT = {**MOCK_FACTS, "certifications": []}


# ── Test 1: Vendor with missing cert fails mandatory check ─────────────────────

async def test_vendor_fails_mandatory_check():
    setup = make_evaluation_setup(has_mandatory_checks=True)

    compliance_response = json.dumps({
        "decision": "fail",
        "confidence": 0.95,
        "reasoning": "No certification found in extracted facts.",
        "evidence_used": [],
        "contradictions_found": [],
        "decision_basis": "not_addressed",
    })
    score_response = json.dumps({
        "raw_score": 7,
        "confidence": 0.8,
        "rubric_band_applied": "6-8",
        "evidence_used": ["P1 response within 30 minutes"],
        "score_rationale": "Strong SLA commitments present.",
        "variance_estimate": 0.5,
    })

    call_llm_mock = AsyncMock(side_effect=[compliance_response, score_response])
    facts_mock = MagicMock(return_value=MOCK_FACTS_NO_CERT)

    with patch("app.agents.evaluation.call_llm", call_llm_mock), \
         patch("app.agents.evaluation.get_vendor_facts", facts_mock):
        from app.agents.evaluation import run_evaluation_agent
        output, critic = await run_evaluation_agent(
            vendor_id="vendor-beta",
            org_id="org-test",
            evaluation_setup=setup,
        )

    assert output.overall_compliance == "fail", f"Expected fail, got {output.overall_compliance}"
    assert any(d.decision == ComplianceStatus.FAIL for d in output.compliance_decisions)
    assert isinstance(output.total_weighted_score, float)
    print("  Test 1 passed: vendor with missing criterion fails deterministically")


# ── Test 2: Vendor with all criteria present passes ────────────────────────────

async def test_vendor_passes_mandatory_check():
    setup = make_evaluation_setup(has_mandatory_checks=True)

    compliance_response = json.dumps({
        "decision": "pass",
        "confidence": 0.95,
        "reasoning": "Current certification found in extracted facts.",
        "evidence_used": ["We hold a current accredited security certification."],
        "contradictions_found": [],
        "decision_basis": "explicit_confirmation",
    })
    score_response = json.dumps({
        "raw_score": 9,
        "confidence": 0.9,
        "rubric_band_applied": "9-10",
        "evidence_used": ["P1 response within 30 minutes, 99.9% uptime guaranteed."],
        "score_rationale": "Excellent SLA commitments.",
        "variance_estimate": 0.3,
    })

    call_llm_mock = AsyncMock(side_effect=[compliance_response, score_response])
    facts_mock = MagicMock(return_value=MOCK_FACTS)

    with patch("app.agents.evaluation.call_llm", call_llm_mock), \
         patch("app.agents.evaluation.get_vendor_facts", facts_mock):
        from app.agents.evaluation import run_evaluation_agent
        output, critic = await run_evaluation_agent(
            vendor_id="vendor-alpha",
            org_id="org-test",
            evaluation_setup=setup,
        )

    assert output.overall_compliance == "pass", f"Expected pass, got {output.overall_compliance}"
    assert all(d.decision == ComplianceStatus.PASS for d in output.compliance_decisions)
    print("  Test 2 passed: vendor with all criteria present passes compliance check")


# ── Test 3: CriterionScore includes variance_estimate ─────────────────────────

async def test_criterion_score_has_variance():
    setup = make_evaluation_setup(has_mandatory_checks=False)

    score_response = json.dumps({
        "raw_score": 6,
        "confidence": 0.75,
        "rubric_band_applied": "6-8",
        "evidence_used": ["SLA response within 2 hours."],
        "score_rationale": "Adequate SLA commitments.",
        "variance_estimate": 1.5,
    })

    call_llm_mock = AsyncMock(return_value=score_response)
    facts_mock = MagicMock(return_value=MOCK_FACTS)

    with patch("app.agents.evaluation.call_llm", call_llm_mock), \
         patch("app.agents.evaluation.get_vendor_facts", facts_mock):
        from app.agents.evaluation import run_evaluation_agent
        output, _ = await run_evaluation_agent(
            vendor_id="vendor-gamma",
            org_id="org-test",
            evaluation_setup=setup,
        )

    assert output.criterion_scores, "Expected at least one criterion score"
    score = output.criterion_scores[0]
    assert hasattr(score, "variance_estimate"), "CriterionScore missing variance_estimate"
    assert isinstance(score.variance_estimate, float)
    print(f"  Test 3 passed: CriterionScore.variance_estimate = {score.variance_estimate}")


# ── Test 4: Comparator produces stable ranking ────────────────────────────────

async def test_comparator_stable_ranking():
    setup = make_evaluation_setup(has_mandatory_checks=False)

    eval_alpha = EvaluationOutput(
        evaluation_id=str(uuid.uuid4()),
        vendor_id="vendor-alpha",
        compliance_decisions=[],
        criterion_scores=[
            CriterionScore(
                criterion_id="crit-sla",
                vendor_id="vendor-alpha",
                raw_score=9,
                weighted_contribution=0.9,
                confidence=0.9,
                rubric_band_applied="9-10",
                evidence_used=["99.9% uptime"],
                score_rationale="Excellent",
                variance_estimate=0.3,
            )
        ],
        overall_compliance="pass",
        total_weighted_score=0.9,
        score_confidence=0.9,
    )
    eval_beta = EvaluationOutput(
        evaluation_id=str(uuid.uuid4()),
        vendor_id="vendor-beta",
        compliance_decisions=[],
        criterion_scores=[
            CriterionScore(
                criterion_id="crit-sla",
                vendor_id="vendor-beta",
                raw_score=5,
                weighted_contribution=0.5,
                confidence=0.7,
                rubric_band_applied="3-5",
                evidence_used=["8 hour response"],
                score_rationale="Adequate",
                variance_estimate=1.0,
            )
        ],
        overall_compliance="pass",
        total_weighted_score=0.5,
        score_confidence=0.7,
    )

    compare_response = json.dumps({
        "vendor_differentiators": {
            "vendor-alpha": "Best-in-class uptime guarantee",
            "vendor-beta": "Basic SLA commitments only",
        },
        "distinguishing_factors": "vendor-alpha leads significantly on uptime and response time",
        "comparison_confidence": 0.85,
    })

    facts_mock = MagicMock(return_value=MOCK_FACTS)
    call_llm_mock = AsyncMock(return_value=compare_response)

    with patch("app.agents.comparator.call_llm", call_llm_mock), \
         patch("app.agents.comparator.get_vendor_facts", facts_mock):
        from app.agents.comparator import run_comparator_agent
        output, critic = await run_comparator_agent(
            vendor_ids=["vendor-alpha", "vendor-beta"],
            org_id="org-test",
            rfp_id="rfp-test",
            evaluation_setup=setup,
            evaluation_outputs={"vendor-alpha": eval_alpha, "vendor-beta": eval_beta},
        )

    assert output.overall_ranking[0] == "vendor-alpha", \
        f"Expected vendor-alpha top, got {output.overall_ranking}"
    assert len(output.criteria_comparisons) == 1
    assert output.criteria_comparisons[0].rank_stable is True
    print(f"  Test 4 passed: stable ranking {output.overall_ranking}, confidence={output.ranking_confidence}")


# ── Runner ─────────────────────────────────────────────────────────────────────

async def main():
    print("Running procurement evaluation pipeline tests...")
    try:
        await test_vendor_fails_mandatory_check()
        await test_vendor_passes_mandatory_check()
        await test_criterion_score_has_variance()
        await test_comparator_stable_ranking()
        print("\nPASSED — all 4 procurement agent tests passed")
    except AssertionError as e:
        print(f"\nFAILED: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
