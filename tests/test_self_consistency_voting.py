"""
P1.7 — self-consistency voting for BORDERLINE mandatory compliance checks.

A mandatory check is normally one temperature-0 LLM call. When that first call's
confidence falls inside the configured borderline band the verdict is fragile, so the
same decision is resampled `samples` times and the MAJORITY wins. No strict majority →
fail-safe insufficient_evidence (owner decision).

These tests cover the exit criteria in docs/dev/P1.7.md:
  • band-outside  → exactly ONE call, behaviour unchanged
  • band-inside   → N calls + majority decision (2×pass+1×fail → pass)
  • no majority   → insufficient_evidence (1/1/1 three-way tie)
  • voted confidence == agreement ratio (winning votes / samples) + vote_breakdown audit
  • enabled=false → single call (identical to today)
  • the E3.b contradiction override still forces insufficient on a "pass" majority

call_llm is mocked — these are isolated unit/integration tests, no network.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.agents.evaluation import _decide_check_with_voting, _evaluate_mandatory_check
from app.schemas.output_models import ComplianceStatus
from app.schemas.schema_setup import MandatoryCheck, ExtractionTarget


# ── helpers ──────────────────────────────────────────────────────────────────

def _resp(decision: str, confidence: float, *, contradictions=None) -> str:
    return json.dumps({
        "decision": decision,
        "confidence": confidence,
        "reasoning": "because",
        "evidence_used": ["verbatim quote"],
        "contradictions_found": contradictions or [],
        "decision_basis": "explicit_confirmation",
    })


def _mock_llm(*responses: str) -> AsyncMock:
    """An AsyncMock for call_llm that yields the given responses in order."""
    return AsyncMock(side_effect=list(responses))


_MESSAGES = [{"role": "user", "content": "decide this check"}]


@pytest.fixture
def sc_config():
    """Snapshot + restore the live self_consistency config so each test can tune it
    without polluting the others (last-write-wins pollution guard)."""
    sc = settings.platform.self_consistency
    saved = sc.model_dump()
    # Deterministic defaults for the tests (mirror the spec).
    sc.enabled = True
    sc.samples = 3
    sc.confidence_min = 0.5
    sc.confidence_max = 0.75
    sc.temperature = 0.5
    yield sc
    for k, v in saved.items():
        setattr(sc, k, v)


def _check_and_target():
    check = MandatoryCheck(
        check_id="chk-1", name="ISO 27001", description="holds ISO 27001",
        what_passes="valid ISO 27001 certificate", extraction_target_id="t-1",
    )
    target = ExtractionTarget(
        target_id="t-1", name="ISO cert", description="certification record",
        fact_type="certification", is_mandatory=True,
    )
    return check, target


# ── _decide_check_with_voting (unit) ─────────────────────────────────────────

async def test_band_outside_makes_one_call(sc_config):
    """Exit #1 — confidence outside the band → exactly one LLM call, no voting."""
    mock = _mock_llm(_resp("pass", 0.95))
    with patch("app.agents.evaluation.call_llm", mock):
        parsed, votes = await _decide_check_with_voting(_MESSAGES)
    assert mock.call_count == 1
    assert votes == {"samples": 1}
    assert parsed["decision"] == "pass"
    assert parsed["confidence"] == 0.95  # untouched — no agreement-ratio rewrite


async def test_band_inside_votes_majority(sc_config):
    """Exit #2 — borderline primary → `samples` calls; 2×pass + 1×fail → pass."""
    mock = _mock_llm(_resp("pass", 0.6), _resp("pass", 0.55), _resp("fail", 0.7))
    with patch("app.agents.evaluation.call_llm", mock):
        parsed, votes = await _decide_check_with_voting(_MESSAGES)
    assert mock.call_count == 3
    assert parsed["decision"] == "pass"
    assert votes["samples"] == 3
    assert votes["tally"] == {"pass": 2, "fail": 1}
    assert votes["winner"] == "pass"


async def test_no_majority_is_insufficient(sc_config):
    """Exit #3 — a 1/1/1 three-way split has no strict majority → insufficient_evidence,
    regardless of which sample was most confident."""
    mock = _mock_llm(
        _resp("pass", 0.7),            # most confident, but no majority
        _resp("fail", 0.6),
        _resp("insufficient_evidence", 0.5),
    )
    with patch("app.agents.evaluation.call_llm", mock):
        parsed, votes = await _decide_check_with_voting(_MESSAGES)
    assert parsed["decision"] == "insufficient_evidence"
    assert votes["winner"] == "insufficient_evidence"
    # agreement ratio: the lone insufficient vote / 3 samples
    assert parsed["confidence"] == pytest.approx(1 / 3)


async def test_voted_confidence_is_agreement_ratio(sc_config):
    """Exit #4 — reported confidence after a vote = winning votes / samples."""
    mock = _mock_llm(_resp("pass", 0.6), _resp("pass", 0.51), _resp("fail", 0.74))
    with patch("app.agents.evaluation.call_llm", mock):
        parsed, votes = await _decide_check_with_voting(_MESSAGES)
    assert parsed["confidence"] == pytest.approx(2 / 3)
    assert votes == {"samples": 3, "tally": {"pass": 2, "fail": 1}, "winner": "pass"}


async def test_disabled_makes_one_call(sc_config):
    """Exit #5 — enabled=false → single call even for a borderline confidence."""
    sc_config.enabled = False
    mock = _mock_llm(_resp("pass", 0.6))  # 0.6 is inside the band, but voting is off
    with patch("app.agents.evaluation.call_llm", mock):
        parsed, votes = await _decide_check_with_voting(_MESSAGES)
    assert mock.call_count == 1
    assert votes == {"samples": 1}
    assert parsed["confidence"] == 0.6


async def test_representative_carries_winning_sample_reasoning(sc_config):
    """The representative dict is the highest-confidence sample of the winning decision —
    so the reasoning/evidence handed downstream belong to the winner."""
    mock = _mock_llm(
        json.dumps({"decision": "pass", "confidence": 0.6, "reasoning": "low-conf pass",
                    "evidence_used": ["a"], "contradictions_found": [], "decision_basis": "explicit_confirmation"}),
        json.dumps({"decision": "pass", "confidence": 0.74, "reasoning": "high-conf pass",
                    "evidence_used": ["b"], "contradictions_found": [], "decision_basis": "explicit_confirmation"}),
        _resp("fail", 0.55),
    )
    with patch("app.agents.evaluation.call_llm", mock):
        parsed, _ = await _decide_check_with_voting(_MESSAGES)
    assert parsed["reasoning"] == "high-conf pass"
    assert parsed["evidence_used"] == ["b"]


# ── _evaluate_mandatory_check (integration) ──────────────────────────────────

async def test_integration_borderline_vote_populates_breakdown(sc_config):
    """Exit #2 + module map — end-to-end through _evaluate_mandatory_check: a borderline
    primary with divergent samples yields a ComplianceDecision carrying vote_breakdown."""
    check, target = _check_and_target()
    facts = [{"value": "ISO 27001", "grounding_quote": "holds ISO 27001"}]
    mock = _mock_llm(_resp("pass", 0.6), _resp("pass", 0.7), _resp("fail", 0.55))
    with patch("app.agents.evaluation.call_llm", mock):
        # org_id="" → chunk fallback is skipped (isolates the voting path)
        decision = await _evaluate_mandatory_check(check, target, facts, "acme", org_id="")
    assert decision.decision == ComplianceStatus.PASS
    assert decision.confidence == pytest.approx(2 / 3)
    assert decision.vote_breakdown["winner"] == "pass"
    assert decision.vote_breakdown["samples"] == 3


async def test_integration_contradiction_override_after_majority(sc_config):
    """Exit #6 (regression) — the E3.b contradiction override still forces insufficient
    even when voting produced a `pass` majority, because the representative pass sample
    carries a contradiction."""
    check, target = _check_and_target()
    facts = [{"value": "ISO 27001", "grounding_quote": "holds ISO 27001"}]
    mock = _mock_llm(
        _resp("pass", 0.6, contradictions=["cert expired"]),  # highest-conf pass → representative
        _resp("pass", 0.55),
        _resp("fail", 0.7),
    )
    with patch("app.agents.evaluation.call_llm", mock):
        decision = await _evaluate_mandatory_check(check, target, facts, "acme", org_id="")
    # majority was pass, but the override wins → insufficient_evidence
    assert decision.decision == ComplianceStatus.INSUFFICIENT_EVIDENCE
    assert decision.vote_breakdown["winner"] == "pass"
