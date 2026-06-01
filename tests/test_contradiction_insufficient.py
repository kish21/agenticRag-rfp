"""
E3.b — a flagged contradiction forces insufficient_evidence (no API needed).

When the evaluate_check LLM reports conflicting values in `contradictions_found`,
the mandatory-check decision must become insufficient_evidence regardless of the
proposed decision, and the optimistic chunk-fallback must not flip it to PASS.
"""
from __future__ import annotations

import asyncio
import json

import app.agents.evaluation as ev
from app.agents.evaluation import _evaluate_mandatory_check
from app.schemas.output_models import ComplianceStatus, ExtractionTarget, MandatoryCheck

_CHECK = MandatoryCheck(check_id="chk-pi", name="PI insurance >= £5M",
                        description="must hold PI insurance of at least £5M",
                        what_passes="cover of £5,000,000+", extraction_target_id="ext-pi")
_TARGET = ExtractionTarget(target_id="ext-pi", name="PI insurance",
                           description="PI insurance amount", fact_type="insurance",
                           is_mandatory=True)


def _patch_llm(monkeypatch, payload: dict):
    async def _fake(*a, **k):
        return json.dumps(payload)
    monkeypatch.setattr(ev, "call_llm", _fake)


def test_contradiction_forces_insufficient_even_if_llm_says_pass(monkeypatch):
    _patch_llm(monkeypatch, {
        "decision": "pass", "confidence": 0.9, "reasoning": "found £10M",
        "evidence_used": ["£10,000,000"],
        "contradictions_found": ["£10,000,000", "£2,000,000"],
        "decision_basis": "explicit_confirmation",
    })
    dec = asyncio.run(_evaluate_mandatory_check(
        _CHECK, _TARGET, [{"amount": 10000000}, {"amount": 2000000}], "v1"))
    assert dec.decision == ComplianceStatus.INSUFFICIENT_EVIDENCE
    assert dec.contradictions_found == ["£10,000,000", "£2,000,000"]


def test_no_contradiction_passes_through(monkeypatch):
    _patch_llm(monkeypatch, {
        "decision": "pass", "confidence": 0.9, "reasoning": "ok",
        "evidence_used": ["£10,000,000"], "contradictions_found": [],
        "decision_basis": "explicit_confirmation",
    })
    dec = asyncio.run(_evaluate_mandatory_check(
        _CHECK, _TARGET, [{"amount": 10000000}], "v1"))
    assert dec.decision == ComplianceStatus.PASS


# ── Report completes for a system-determined (rejection/conflict) narrative ────

from app.agents.critic import critic_after_explanation
from app.schemas.output_models import (
    ExplanationOutput, VendorNarrative, SystemFact, CriticSeverity,
)


def _narr(vendor_id, removed=0, system_facts=None):
    return VendorNarrative(
        vendor_id=vendor_id, vendor_name=vendor_id, executive_summary="",
        compliance_narrative="", scoring_narrative="", recommendation_rationale="",
        grounded_claims=[], ungrounded_claims_removed=removed,
        system_facts=system_facts or [],
    )


def _hard_flags(critic_out):
    return {f.check_name for f in critic_out.flags if f.severity == CriticSeverity.HARD}


def test_system_fact_only_narrative_is_not_empty_block():
    # A rejected/conflicted vendor whose story is system_facts (no PDF claims) must
    # NOT be HARD-blocked as 'empty' — that IS the report content the customer needs.
    narr = _narr("epsilon", system_facts=[
        SystemFact(fact_text="Rejected — conflicting PI insurance £10M vs £2M.",
                   origin="evaluation", origin_id="chk-pi")])
    out = ExplanationOutput(
        explanation_id="x", executive_summary="", vendor_narratives=[narr],
        methodology_note="", grounding_completeness=1.0, report_confidence=0.8)
    assert "empty_narrative" not in _hard_flags(critic_after_explanation(out, {}))


def test_truly_empty_narrative_still_blocks():
    # No PDF claims, none removed, AND no system_facts → still a HARD empty block
    # (the honesty guardrail is untouched for genuinely empty output).
    out = ExplanationOutput(
        explanation_id="x", executive_summary="", vendor_narratives=[_narr("ghost")],
        methodology_note="", grounding_completeness=1.0, report_confidence=0.8)
    assert "empty_narrative" in _hard_flags(critic_after_explanation(out, {}))


# ── E3.b.2 — a RESOLVED contradiction is SOFT, so the vendor stays in the report ─
# (instead of being HARD-blocked → retried → dropped, which made the benchmark
#  grader score the contradicted vendor as an artifact). A contradiction that
#  co-exists with a PASS/FAIL is still HARD: the decision is genuinely unreliable.

from app.agents.critic import critic_after_evaluation
from app.schemas.output_models import (
    EvaluationOutput, ComplianceDecision, DecisionBasis, ExtractionOutput,
    CriticVerdict,
)


def _eval_out(decision: ComplianceStatus):
    dec = ComplianceDecision(
        check_id="MC-001", vendor_id="epsilon", decision=decision, confidence=0.6,
        reasoning="conflicting evidence", evidence_used=["£10M", "£2M"],
        contradictions_found=["£10,000,000", "£2,000,000"],
        decision_basis=DecisionBasis.PARTIAL_COMPLIANCE)
    return EvaluationOutput(
        evaluation_id="e1", vendor_id="epsilon", compliance_decisions=[dec],
        criterion_scores=[], overall_compliance="review_required",
        total_weighted_score=0.0, score_confidence=0.6)


_STUB_EXTRACTION = ExtractionOutput(
    extraction_id="ex1", vendor_id="epsilon", org_id="org1", source_chunk_ids=[],
    extraction_completeness=0.8, hallucination_risk=0.1)


def test_resolved_contradiction_is_soft_not_blocked():
    # Contradiction already resolved to insufficient_evidence → SOFT, NOT BLOCKED,
    # so run_with_critic_retry keeps the vendor in evaluation_output_objects.
    critic = critic_after_evaluation(
        _eval_out(ComplianceStatus.INSUFFICIENT_EVIDENCE), _STUB_EXTRACTION)
    assert critic.overall_verdict != CriticVerdict.BLOCKED
    soft = {f.check_name for f in critic.flags if f.severity == CriticSeverity.SOFT}
    assert "contradictions_in_evidence" in soft


def test_unresolved_contradiction_on_pass_still_blocks():
    # A PASS that still carries a contradiction is unreliable → stays HARD (Q07).
    critic = critic_after_evaluation(
        _eval_out(ComplianceStatus.PASS), _STUB_EXTRACTION)
    assert critic.overall_verdict == CriticVerdict.BLOCKED
