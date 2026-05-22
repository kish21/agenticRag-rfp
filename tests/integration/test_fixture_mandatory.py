#!/usr/bin/env python3
"""
Fixture regression test for mandatory check evaluator.

Tests three scenarios:
  1. Facts present in PostgreSQL → evaluation uses facts directly
  2. Facts absent, chunk satisfies threshold → fallback returns pass
  3. Facts absent, no chunk satisfies threshold → returns insufficient_evidence

Run with:
    python scripts/test_fixture_mandatory.py
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.agents.evaluation import _evaluate_mandatory_check, _llm_verify_threshold
from app.core.output_models import (
    ComplianceStatus, MandatoryCheck, ExtractionTarget,
)

ISO_CHECK = MandatoryCheck(
    check_id="chk-iso",
    name="Information Security Certification",
    description="Vendor must hold a current ISO 27001 certification.",
    what_passes=(
        "ISO 27001 certificate number stated, issuing body named, "
        "valid-until date confirmed as after 1 September 2026"
    ),
    extraction_target_id="tgt-cert",
    mandatory=True,
)

TARGET = ExtractionTarget(
    target_id="tgt-cert",
    name="Certifications",
    description="Security and quality certifications held by the vendor.",
    fact_type="certification",
    is_mandatory=True,
    feeds_check_id="chk-iso",
)

ISO_FACT = {
    "name": "ISO 27001",
    "issuing_body": "BSI Group",
    "certificate_number": "IS 123456",
    "valid_until": "2027-03-15",
    "grounding_quote": "We hold ISO 27001 certification (IS 123456) issued by BSI Group, valid until 15 March 2027.",
}

CHUNK_WITH_ISO = (
    "Apex Technology holds ISO 27001 certification issued by BSI Group. "
    "Certificate number IS 123456, valid until 15 March 2027. "
    "Our security controls are audited annually by an accredited third party."
)

CHUNK_WITHOUT_ISO = (
    "We take information security seriously and follow industry best practices. "
    "Our team undergoes regular security training."
)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def _llm_response_for_facts(decision: str, confidence: float = 0.9) -> str:
    import json
    return json.dumps({
        "decision": decision,
        "confidence": confidence,
        "reasoning": "Test fixture response",
        "evidence_used": ["IS 123456"],
        "contradictions_found": [],
        "decision_basis": "explicit_confirmation",
    })


def _verify_response(satisfies: bool, evidence: str = "") -> str:
    import json
    return json.dumps({
        "satisfies": satisfies,
        "evidence": evidence,
        "confidence": 0.95 if satisfies else 0.1,
    })


async def test_facts_present_pass():
    """When PostgreSQL has the right facts, evaluator returns pass without hitting Qdrant."""
    with patch(
        "app.agents.evaluation.call_llm",
        new_callable=AsyncMock,
        return_value=_llm_response_for_facts("pass"),
    ):
        result = await _evaluate_mandatory_check(
            ISO_CHECK, TARGET, [ISO_FACT], "vendor-a", "org-1"
        )
    assert result.decision == ComplianceStatus.PASS, f"Expected pass, got {result.decision}"
    print(f"  {PASS}  test_facts_present_pass")


async def test_facts_absent_chunk_passes():
    """When PostgreSQL has no facts but a chunk satisfies the threshold, returns pass."""
    llm_calls = [
        _llm_response_for_facts("insufficient_evidence", 0.3),
        _verify_response(False, ""),
        _verify_response(True, "Certificate number IS 123456, valid until 15 March 2027"),
    ]
    call_iter = iter(llm_calls)

    async def mock_llm(*args, **kwargs):
        return next(call_iter)

    mock_chunks = [
        {"text": CHUNK_WITHOUT_ISO, "chunk_id": "c1", "score": 0.85},
        {"text": CHUNK_WITH_ISO, "chunk_id": "c2", "score": 0.91},
    ]

    with patch("app.agents.evaluation.call_llm", side_effect=mock_llm), \
         patch("app.agents.evaluation._retrieve_top_k_for_check", return_value=mock_chunks):
        result = await _evaluate_mandatory_check(
            ISO_CHECK, TARGET, [], "vendor-a", "org-1"
        )

    assert result.decision == ComplianceStatus.PASS, f"Expected pass, got {result.decision}"
    assert result.evidence_used, "Expected evidence from chunk verification"
    print(f"  {PASS}  test_facts_absent_chunk_passes")


async def test_facts_absent_no_chunk_satisfies():
    """When PostgreSQL has no facts and no chunk satisfies the threshold, returns insufficient_evidence."""
    llm_calls = [
        _llm_response_for_facts("insufficient_evidence", 0.2),
        _verify_response(False, ""),
        _verify_response(False, ""),
    ]
    call_iter = iter(llm_calls)

    async def mock_llm(*args, **kwargs):
        return next(call_iter)

    mock_chunks = [
        {"text": CHUNK_WITHOUT_ISO, "chunk_id": "c1", "score": 0.6},
        {"text": "We are committed to quality.", "chunk_id": "c2", "score": 0.5},
    ]

    with patch("app.agents.evaluation.call_llm", side_effect=mock_llm), \
         patch("app.agents.evaluation._retrieve_top_k_for_check", return_value=mock_chunks):
        result = await _evaluate_mandatory_check(
            ISO_CHECK, TARGET, [], "vendor-a", "org-1"
        )

    assert result.decision == ComplianceStatus.INSUFFICIENT_EVIDENCE, (
        f"Expected insufficient_evidence, got {result.decision}"
    )
    print(f"  {PASS}  test_facts_absent_no_chunk_satisfies")


async def test_no_org_id_no_fallback():
    """When org_id is empty, fallback retrieval is skipped (prevents unintentional Qdrant calls)."""
    with patch(
        "app.agents.evaluation.call_llm",
        new_callable=AsyncMock,
        return_value=_llm_response_for_facts("insufficient_evidence", 0.2),
    ), patch(
        "app.agents.evaluation._retrieve_top_k_for_check",
        return_value=[{"text": CHUNK_WITH_ISO, "chunk_id": "c1", "score": 0.9}],
    ) as mock_retrieve:
        result = await _evaluate_mandatory_check(
            ISO_CHECK, TARGET, [], "vendor-a", ""
        )
    mock_retrieve.assert_not_called()
    assert result.decision == ComplianceStatus.INSUFFICIENT_EVIDENCE
    print(f"  {PASS}  test_no_org_id_no_fallback")


async def main():
    print("\n--- Mandatory Check Evaluator Fixture Tests ---\n")
    tests = [
        test_facts_present_pass,
        test_facts_absent_chunk_passes,
        test_facts_absent_no_chunk_satisfies,
        test_no_org_id_no_fallback,
    ]
    failures = 0
    for test in tests:
        try:
            await test()
        except Exception as e:
            print(f"  \033[91mFAIL\033[0m  {test.__name__}: {e}")
            failures += 1

    print(f"\n{'All tests passed' if not failures else f'{failures} test(s) failed'}\n")
    sys.exit(failures)


if __name__ == "__main__":
    asyncio.run(main())
