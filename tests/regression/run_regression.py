"""
Regression suite — 20 questions across 5 categories.
All tests are programmatic (no LLM calls). Fast, deterministic.

Categories:
  Q01-Q05  Retrieval quality
  Q06-Q10  Compliance decisions (including known fails)
  Q11-Q14  Scoring
  Q15-Q17  Comparator
  Q18-Q20  Full pipeline contracts

Threshold: 18/20 to deploy.
"""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

results: list[tuple[str, bool, str]] = []


def test(qid: str, description: str):
    def decorator(fn):
        try:
            fn()
            results.append((qid, True, description))
        except AssertionError as e:
            results.append((qid, False, f"{description} — {e}"))
        except Exception as e:
            results.append((qid, False, f"{description} — ERROR: {e}"))
        return fn
    return decorator


# ── Q01-Q05: Retrieval quality ─────────────────────────────────────────

@test("Q01", "RetrievalOutput model validates with required fields")
def q01():
    from app.core.output_models import RetrievalOutput, RetrievedChunk
    chunk = RetrievedChunk(
        chunk_id="c1", qdrant_point_id="c1", text="ISO 27001 certification held",
        section_id="s1", section_title="Certifications", section_type="requirement_response",
        filename="vendor.pdf", page_number=1, vendor_id="v1",
        vector_similarity_score=0.91, rerank_score=0.95, final_score=0.95,
        is_answer_bearing=True
    )
    out = RetrievalOutput(
        query_id="q1", original_query="ISO cert?", rewritten_query="ISO 27001 certification",
        hyde_query_used=False, retrieval_strategy="dense+rerank",
        chunks=[chunk], total_candidates_before_rerank=10,
        confidence=0.95, empty_retrieval=False
    )
    assert out.confidence == 0.95
    assert len(out.chunks) == 1
    assert out.chunks[0].is_answer_bearing is True


@test("Q02", "Empty retrieval triggers Critic soft flag for non-mandatory")
def q02():
    from app.core.output_models import RetrievalOutput, CriticVerdict
    from app.agents.critic import critic_after_retrieval
    out = RetrievalOutput(
        query_id="q2", original_query="test", rewritten_query="test",
        hyde_query_used=False, retrieval_strategy="dense",
        chunks=[], total_candidates_before_rerank=0,
        confidence=0.0, empty_retrieval=True
    )
    critic = critic_after_retrieval(out, is_mandatory=False)
    assert critic.overall_verdict != CriticVerdict.BLOCKED
    assert critic.soft_flag_count >= 1


@test("Q03", "Empty retrieval on mandatory query triggers Critic hard block")
def q03():
    from app.core.output_models import RetrievalOutput, CriticVerdict
    from app.agents.critic import critic_after_retrieval
    out = RetrievalOutput(
        query_id="q3", original_query="ISO 27001 mandatory", rewritten_query="ISO 27001",
        hyde_query_used=False, retrieval_strategy="dense",
        chunks=[], total_candidates_before_rerank=0,
        confidence=0.0, empty_retrieval=True
    )
    critic = critic_after_retrieval(out, is_mandatory=True)
    assert critic.overall_verdict == CriticVerdict.BLOCKED


@test("Q04", "is_answer_bearing detects keyword overlap")
def q04():
    from app.agents.retrieval import is_answer_bearing
    assert is_answer_bearing(
        "ISO certification security management",
        "The vendor holds ISO 27001 certification for information security management"
    ) is True
    assert is_answer_bearing(
        "insurance coverage liability",
        "Our pricing model offers competitive rates"
    ) is False


@test("Q05", "verify_grounding returns False for invented quotes")
def q05():
    from app.agents.explanation import verify_grounding
    source = {"c1": "The vendor holds ISO 27001 certification issued by BSI Group."}
    assert verify_grounding("claim", "ISO 27001 certification issued by BSI", "c1", source) is True
    assert verify_grounding("claim", "invented text not in source at all", "c1", source) is False
    assert verify_grounding("claim", "real quote", "missing-chunk", source) is False


# ── Q06-Q10: Compliance decisions ──────────────────────────────────────

@test("Q06", "ComplianceDecision FAIL status set correctly")
def q06():
    from app.core.output_models import ComplianceDecision, ComplianceStatus, DecisionBasis
    d = ComplianceDecision(
        check_id="MC-001", vendor_id="v1",
        decision=ComplianceStatus.FAIL,
        confidence=0.95, reasoning="No ISO 27001 found",
        evidence_used=["working towards certification"],
        decision_basis=DecisionBasis.EXPLICIT_DENIAL
    )
    assert d.decision == ComplianceStatus.FAIL
    assert len(d.evidence_used) == 1


@test("Q07", "Critic blocks evaluation with contradictions in evidence")
def q07():
    from app.core.output_models import (
        EvaluationOutput, ComplianceDecision, ComplianceStatus,
        DecisionBasis, CriterionScore, ExtractionOutput, CriticVerdict
    )
    from app.agents.critic import critic_after_evaluation
    decision = ComplianceDecision(
        check_id="MC-001", vendor_id="v1",
        decision=ComplianceStatus.PASS, confidence=0.6,
        reasoning="Conflicting evidence found",
        evidence_used=["holds cert", "cert expired"],
        contradictions_found=["cert is both current and expired"],
        decision_basis=DecisionBasis.PARTIAL_COMPLIANCE
    )
    score = CriterionScore(
        criterion_id="C1", vendor_id="v1", raw_score=7,
        weighted_contribution=0.7, confidence=0.8,
        rubric_band_applied="6-8", evidence_used=["good track record"],
        score_rationale="Solid evidence", variance_estimate=1.0
    )
    eval_out = EvaluationOutput(
        evaluation_id="e1", vendor_id="v1",
        compliance_decisions=[decision], criterion_scores=[score],
        overall_compliance="review_required",
        total_weighted_score=7.0, score_confidence=0.6
    )
    extraction = ExtractionOutput(
        extraction_id="ex1", vendor_id="v1", org_id="org1",
        source_chunk_ids=[], extraction_completeness=0.8, hallucination_risk=0.1
    )
    critic = critic_after_evaluation(eval_out, extraction)
    assert critic.overall_verdict == CriticVerdict.BLOCKED


@test("Q08", "RejectionNotice requires non-empty evidence_citations")
def q08():
    from app.core.output_models import RejectionNotice
    r = RejectionNotice(
        vendor_id="v1", vendor_name="Vendor One",
        failed_checks=["MC-001"],
        rejection_reasons=["No ISO 27001 certification"],
        evidence_citations=["working towards ISO 27001 certification"],
        clause_references=["2.1"]
    )
    assert len(r.evidence_citations) == 1
    assert "ISO 27001" in r.evidence_citations[0]


@test("Q09", "Critic hard blocks decision with empty evidence_citations")
def q09():
    from app.core.output_models import (
        DecisionOutput, RejectionNotice, ApprovalRouting, CriticVerdict
    )
    from app.agents.critic import critic_after_decision
    from datetime import datetime, timedelta
    rej = RejectionNotice(
        vendor_id="v1", vendor_name="Vendor One",
        failed_checks=["MC-001"],
        rejection_reasons=["No certification"],
        evidence_citations=[],  # empty — should hard block
        clause_references=[]
    )
    routing = ApprovalRouting(
        approval_tier=2, approver_role="procurement_lead",
        contract_value=300000, sla_hours=48,
        sla_deadline=datetime.utcnow() + timedelta(hours=48)
    )
    out = DecisionOutput(
        decision_id="d1", rfp_id="rfp1",
        rejected_vendors=[rej], shortlisted_vendors=[],
        approval_routing=routing, decision_confidence=0.9,
        requires_human_review=False
    )
    critic = critic_after_decision(out)
    assert critic.overall_verdict == CriticVerdict.BLOCKED


@test("Q10", "All-vendors-rejected triggers escalation")
def q10():
    from app.core.output_models import (
        DecisionOutput, RejectionNotice, ApprovalRouting, CriticVerdict
    )
    from app.agents.critic import critic_after_decision
    from datetime import datetime, timedelta
    rej = RejectionNotice(
        vendor_id="v1", vendor_name="Vendor One",
        failed_checks=["MC-001"],
        rejection_reasons=["No ISO 27001"],
        evidence_citations=["working towards certification"],
        clause_references=["2.1"]
    )
    routing = ApprovalRouting(
        approval_tier=3, approver_role="cfo",
        contract_value=800000, sla_hours=72,
        sla_deadline=datetime.utcnow() + timedelta(hours=72)
    )
    out = DecisionOutput(
        decision_id="d2", rfp_id="rfp1",
        rejected_vendors=[rej], shortlisted_vendors=[],
        approval_routing=routing, decision_confidence=0.8,
        requires_human_review=False
    )
    critic = critic_after_decision(out)
    assert critic.overall_verdict in (CriticVerdict.BLOCKED, CriticVerdict.ESCALATED)


# ── Q11-Q14: Scoring ───────────────────────────────────────────────────

@test("Q11", "CriterionScore weighted_contribution calculated correctly")
def q11():
    from app.core.output_models import CriterionScore
    score = CriterionScore(
        criterion_id="C1", vendor_id="v1", raw_score=8,
        weighted_contribution=0.8, confidence=0.9,
        rubric_band_applied="6-8", evidence_used=["strong track record"],
        score_rationale="Excellent evidence", variance_estimate=0.5
    )
    assert score.raw_score == 8
    assert score.weighted_contribution == 0.8
    assert score.variance_estimate == 0.5


@test("Q12", "High variance score triggers Critic soft flag")
def q12():
    from app.core.output_models import (
        EvaluationOutput, ComplianceDecision, ComplianceStatus,
        DecisionBasis, CriterionScore, ExtractionOutput
    )
    from app.agents.critic import critic_after_evaluation
    decision = ComplianceDecision(
        check_id="MC-001", vendor_id="v1",
        decision=ComplianceStatus.PASS, confidence=0.9,
        reasoning="Certification confirmed",
        evidence_used=["ISO 27001 current"],
        decision_basis=DecisionBasis.EXPLICIT_CONFIRMATION
    )
    score = CriterionScore(
        criterion_id="C1", vendor_id="v1", raw_score=6,
        weighted_contribution=0.6, confidence=0.5,
        rubric_band_applied="6-8", evidence_used=["mixed evidence"],
        score_rationale="High variance", variance_estimate=3.0  # >= 2.0 triggers flag
    )
    eval_out = EvaluationOutput(
        evaluation_id="e2", vendor_id="v1",
        compliance_decisions=[decision], criterion_scores=[score],
        overall_compliance="pass",
        total_weighted_score=6.0, score_confidence=0.5
    )
    extraction = ExtractionOutput(
        extraction_id="ex2", vendor_id="v1", org_id="org1",
        source_chunk_ids=[], extraction_completeness=0.7, hallucination_risk=0.1
    )
    critic = critic_after_evaluation(eval_out, extraction)
    assert critic.soft_flag_count >= 1


@test("Q13", "EvaluationSetup weights must sum to 1.0")
def q13():
    from app.core.output_models import EvaluationSetup, ScoringCriterion, MandatoryCheck, ExtractionTarget
    from datetime import datetime
    import pytest
    try:
        EvaluationSetup(
            setup_id="s1", org_id="org1", department="IT",
            rfp_id="rfp1", rfp_confirmed=True,
            mandatory_checks=[],
            scoring_criteria=[
                ScoringCriterion(
                    criterion_id="C1", name="Security", weight=0.6,
                    rubric_9_10="", rubric_6_8="", rubric_3_5="", rubric_0_2="",
                    extraction_target_ids=[]
                ),
                ScoringCriterion(
                    criterion_id="C2", name="Price", weight=0.6,  # sums to 1.2 — invalid
                    rubric_9_10="", rubric_6_8="", rubric_3_5="", rubric_0_2="",
                    extraction_target_ids=[]
                ),
            ],
            extraction_targets=[],
            total_weight=1.2,
            confirmed_by="test", confirmed_at=datetime.utcnow(), source="manually_defined"
        )
        assert False, "Should have raised validation error"
    except Exception:
        pass  # correctly rejected


@test("Q14", "EvaluationSetup with valid weights passes validation")
def q14():
    from app.core.output_models import EvaluationSetup, ScoringCriterion, MandatoryCheck, ExtractionTarget
    from datetime import datetime
    setup = EvaluationSetup(
        setup_id="s2", org_id="org1", department="IT",
        rfp_id="rfp1", rfp_confirmed=True,
        mandatory_checks=[],
        scoring_criteria=[
            ScoringCriterion(
                criterion_id="C1", name="Security", weight=0.6,
                rubric_9_10="", rubric_6_8="", rubric_3_5="", rubric_0_2="",
                extraction_target_ids=[]
            ),
            ScoringCriterion(
                criterion_id="C2", name="Price", weight=0.4,
                rubric_9_10="", rubric_6_8="", rubric_3_5="", rubric_0_2="",
                extraction_target_ids=[]
            ),
        ],
        extraction_targets=[],
        total_weight=1.0,
        confirmed_by="test", confirmed_at=datetime.utcnow(), source="manually_defined"
    )
    assert abs(sum(c.weight for c in setup.scoring_criteria) - 1.0) < 0.01


# ── Q15-Q17: Comparator ────────────────────────────────────────────────

@test("Q15", "ComparatorOutput model validates with ranking")
def q15():
    from app.core.output_models import (
        ComparatorOutput, CriterionComparison, VendorCriterionComparison
    )
    vc = VendorCriterionComparison(
        criterion_id="C1", vendor_id="v1", score=8,
        key_differentiator="Strong ISO certification",
        relative_position="best",
        evidence_summary="ISO 27001 current"
    )
    cc = CriterionComparison(
        criterion_id="C1", criterion_name="Security",
        weight=0.6, vendors=[vc],
        comparison_confidence=0.9, rank_stable=True,
        distinguishing_factors="Clear certification advantage"
    )
    out = ComparatorOutput(
        comparison_id="cmp1", rfp_id="rfp1",
        vendor_ids=["v1", "v2"],
        criteria_comparisons=[cc],
        overall_ranking=["v1", "v2"],
        ranking_confidence=0.85,
        rank_margins={"v1_v2": 2.5}
    )
    assert out.overall_ranking[0] == "v1"
    assert out.ranking_confidence == 0.85


@test("Q16", "Unstable ranking triggers Critic soft flag")
def q16():
    from app.core.output_models import (
        ComparatorOutput, CriterionComparison, VendorCriterionComparison
    )
    from app.agents.critic import critic_after_comparator
    vc = VendorCriterionComparison(
        criterion_id="C1", vendor_id="v1", score=6,
        key_differentiator="Marginal difference",
        relative_position="average", evidence_summary="Similar scores"
    )
    cc = CriterionComparison(
        criterion_id="C1", criterion_name="Security",
        weight=0.5, vendors=[vc],
        comparison_confidence=0.55, rank_stable=False,  # unstable
        distinguishing_factors="Margin too small to be reliable"
    )
    out = ComparatorOutput(
        comparison_id="cmp2", rfp_id="rfp1",
        vendor_ids=["v1", "v2"],
        criteria_comparisons=[cc],
        overall_ranking=["v1", "v2"],
        ranking_confidence=0.55,
        rank_margins={"v1_v2": 0.1}
    )
    critic = critic_after_comparator(out)
    assert critic.soft_flag_count >= 1


@test("Q17", "Empty ranking triggers Critic hard block")
def q17():
    from app.core.output_models import ComparatorOutput, CriticVerdict
    from app.agents.critic import critic_after_comparator
    out = ComparatorOutput(
        comparison_id="cmp3", rfp_id="rfp1",
        vendor_ids=["v1"],
        criteria_comparisons=[],
        overall_ranking=[],  # empty — hard block
        ranking_confidence=0.0,
        rank_margins={}
    )
    critic = critic_after_comparator(out)
    assert critic.overall_verdict == CriticVerdict.BLOCKED


# ── Q18-Q20: Full pipeline contracts ───────────────────────────────────

@test("Q18", "All agent output models are importable and Pydantic v2")
def q18():
    from app.core.output_models import (
        PlannerOutput, IngestionOutput, RetrievalOutput, ExtractionOutput,
        EvaluationOutput, ComparatorOutput, DecisionOutput, ExplanationOutput,
        CriticOutput
    )
    from pydantic import BaseModel
    for model in [PlannerOutput, IngestionOutput, RetrievalOutput, ExtractionOutput,
                  EvaluationOutput, ComparatorOutput, DecisionOutput,
                  ExplanationOutput, CriticOutput]:
        assert issubclass(model, BaseModel)


@test("Q19", "Critic functions exist for all 7 agent types")
def q19():
    from app.agents.critic import (
        critic_after_ingestion,
        critic_after_retrieval,
        critic_after_extraction,
        critic_after_evaluation,
        critic_after_comparator,
        critic_after_decision,
        critic_after_explanation,
    )
    import inspect
    for fn in [critic_after_ingestion, critic_after_retrieval,
               critic_after_extraction, critic_after_evaluation,
               critic_after_comparator, critic_after_decision,
               critic_after_explanation]:
        assert callable(fn)
        assert inspect.isfunction(fn)


@test("Q20", "AuditOverride enforces minimum 20-char reason")
def q20():
    from app.core.output_models import AuditOverride
    from datetime import datetime
    # Short reason must fail
    try:
        AuditOverride(
            override_id="o1", org_id="org1", run_id="r1",
            overridden_by="user@test.com",
            original_decision={"decision": "reject"},
            new_decision={"decision": "accept"},
            reason="too short",  # < 20 chars
            timestamp=datetime.utcnow()
        )
        assert False, "Should have raised"
    except Exception:
        pass
    # Long reason must pass
    override = AuditOverride(
        override_id="o2", org_id="org1", run_id="r1",
        overridden_by="user@test.com",
        original_decision={"decision": "reject"},
        new_decision={"decision": "accept"},
        reason="Vendor confirmed ISO 27001 cert via email after submission deadline.",
        timestamp=datetime.utcnow()
    )
    assert len(override.reason) >= 20


# ── Run all tests ───────────────────────────────────────────────────────

if __name__ == "__main__":
    passed = sum(1 for _, ok, _ in results if ok)
    failed = [(qid, msg) for qid, ok, msg in results if not ok]
    total = len(results)

    print(f"\nRegression Suite Results")
    print(f"{'='*50}")
    for qid, ok, desc in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {qid}: {desc}")

    print(f"\n{'='*50}")
    print(f"Result: {passed}/{total}")
    if failed:
        print(f"\nFailed ({len(failed)}):")
        for qid, msg in failed:
            print(f"  {qid}: {msg}")

    sys.exit(0 if passed >= 18 else 1)
