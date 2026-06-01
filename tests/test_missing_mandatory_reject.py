"""
E3.c — a vendor that does not DEMONSTRATE a mandatory requirement is rejected.

A vendor is rejected on a FAIL, or on an undemonstrated mandatory
(INSUFFICIENT_EVIDENCE, no contradiction) — but the undemonstrated path fires
ONLY when the vendor has NO contradicted mandatory check anywhere. So:
  * omega ("no ISO 27001 / no insurance anywhere", zero contradictions) => reject
  * epsilon (insurance £10M vs £2M contradiction) => human review, NOT rejected,
    even though its cert check looks "missing" (the cert contradiction is lost at
    extraction — the vendor-level guard keeps the reject path robust to that).

The rejection notice for a missing mandatory must still carry non-empty
evidence_citations (the absence statement is the grounded basis) so the
decision critic does not HARD-block it as "rejection without evidence".
"""
from __future__ import annotations

import asyncio

import app.agents.decision as dec
from app.agents.decision import _rejecting_decisions, _build_rejection_notice
from app.schemas.output_models import (
    ComplianceDecision, ComplianceStatus, DecisionBasis, EvaluationOutput,
)


def _decision(status: ComplianceStatus, *, contradictions=None, evidence=None,
              reasoning="", check_id="MC-001"):
    return ComplianceDecision(
        check_id=check_id, vendor_id="v1", decision=status, confidence=0.6,
        reasoning=reasoning, evidence_used=evidence or [],
        contradictions_found=contradictions or [],
        decision_basis=DecisionBasis.NOT_ADDRESSED)


def test_fail_is_rejecting():
    assert _rejecting_decisions([_decision(ComplianceStatus.FAIL)])


def test_missing_mandatory_is_rejecting():
    # omega: insufficient, no contradiction anywhere => genuinely undemonstrated => reject
    cds = [_decision(ComplianceStatus.INSUFFICIENT_EVIDENCE, check_id="chk-iso"),
           _decision(ComplianceStatus.INSUFFICIENT_EVIDENCE, check_id="chk-pi")]
    assert len(_rejecting_decisions(cds)) == 2


def test_vendor_with_any_contradiction_is_not_rejected():
    # epsilon: one check contradicted (insurance), the other looks "missing" (cert
    # collapse). Vendor-level guard => NOT rejected (human review).
    cds = [
        _decision(ComplianceStatus.INSUFFICIENT_EVIDENCE, check_id="chk-pi",
                  contradictions=["£10,000,000", "£2,000,000"]),
        _decision(ComplianceStatus.INSUFFICIENT_EVIDENCE, check_id="chk-iso"),
    ]
    assert _rejecting_decisions(cds) == []


def test_fail_still_rejects_even_with_contradiction_elsewhere():
    # An explicit FAIL is unambiguous non-compliance — reject regardless.
    cds = [
        _decision(ComplianceStatus.FAIL, check_id="chk-pi"),
        _decision(ComplianceStatus.INSUFFICIENT_EVIDENCE, check_id="chk-iso",
                  contradictions=["a", "b"]),
    ]
    rej = _rejecting_decisions(cds)
    assert [d.check_id for d in rej] == ["chk-pi"]


def test_pass_is_not_rejecting():
    assert _rejecting_decisions([_decision(ComplianceStatus.PASS)]) == []


def test_missing_mandatory_rejection_notice_has_citations(monkeypatch):
    # The LLM may legitimately find no evidence to extract for a missing item;
    # the notice must still end up with non-empty evidence_citations.
    async def _fake_llm(*a, **k):
        return '{"evidence": []}'
    monkeypatch.setattr(dec, "call_llm", _fake_llm)

    ev = EvaluationOutput(
        evaluation_id="e1", vendor_id="omega",
        compliance_decisions=[
            _decision(ComplianceStatus.INSUFFICIENT_EVIDENCE, reasoning="",
                      check_id="chk-iso27001")],
        criterion_scores=[], overall_compliance="fail",
        total_weighted_score=0.0, score_confidence=0.5)

    notice = asyncio.run(_build_rejection_notice("omega", ev))
    assert notice.failed_checks == ["chk-iso27001"]
    assert notice.evidence_citations, "missing-mandatory rejection must cite a basis"
    assert "not demonstrated" in notice.evidence_citations[0].lower()
