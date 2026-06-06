"""
P1.8 — verification step after synthesis.

The Explanation Agent's structured `grounded_claims` are already quote-verified
upstream. P1.8 adds a SECOND LLM pass that fact-checks the FREE-TEXT narrative
prose (executive_summary / compliance_narrative / scoring_narrative /
recommendation_rationale) against the same evidence, so a plausible-but-
unsupported sentence in the prose is caught before the report is finalised.

These tests cover:
  • verify_narrative_claims() scoring (all-supported, partial, low-confidence)
  • the config toggle (disabled → no LLM call) and the empty-prose short-circuit
  • critic_after_explanation turning a low prose score into HARD/SOFT flags
    against the configured block_below / warn_below bands, and NOT flagging the
    vacuous (verification-free) 1.0.

call_llm is mocked — these are isolated unit tests, no network.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.agents.explanation import verify_narrative_claims
from app.agents.critic import critic_after_explanation
from app.schemas.output_models import (
    ExplanationOutput, VendorNarrative, GroundedClaim, SystemFact, CriticSeverity,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _narr(
    vendor_id="acme",
    *,
    prose="Acme commits to 99.9% uptime and holds ISO 27001.",
    grounded=1,
    prose_verification=None,
    prose_score=1.0,
) -> VendorNarrative:
    return VendorNarrative(
        vendor_id=vendor_id, vendor_name=vendor_id,
        executive_summary=prose,
        compliance_narrative="", scoring_narrative="", recommendation_rationale="",
        grounded_claims=[
            GroundedClaim(claim_text="Acme holds ISO 27001.",
                          grounding_quote="Acme holds ISO 27001.", source_chunk_id="c1")
            for _ in range(grounded)
        ],
        prose_verification=prose_verification or [],
        prose_verification_score=prose_score,
    )


def _exp(narratives, completeness=1.0) -> ExplanationOutput:
    return ExplanationOutput(
        explanation_id="x", executive_summary="", vendor_narratives=narratives,
        methodology_note="", grounding_completeness=completeness, report_confidence=0.8,
    )


def _mock_llm(claims: list[dict]) -> AsyncMock:
    return AsyncMock(return_value=json.dumps({"claims": claims}))


def _flags(critic_out, severity):
    return {f.check_name for f in critic_out.flags if f.severity == severity}


# ── verify_narrative_claims() scoring ────────────────────────────────────────

async def test_all_supported_scores_one():
    narr = _narr()
    mock = _mock_llm([
        {"claim_text": "Acme commits to 99.9% uptime", "supported": True,
         "supporting_chunk_id": "c1", "confidence": 0.95},
        {"claim_text": "Acme holds ISO 27001", "supported": True,
         "supporting_chunk_id": "c1", "confidence": 0.95},
    ])
    with patch("app.agents.explanation.call_llm", mock):
        verifications, score = await verify_narrative_claims(narr, {"c1": "..."})
    assert score == 1.0
    assert len(verifications) == 2
    mock.assert_awaited_once()


async def test_one_unsupported_drops_score():
    narr = _narr()
    mock = _mock_llm([
        {"claim_text": "Acme holds ISO 27001", "supported": True,
         "supporting_chunk_id": "c1", "confidence": 0.9},
        {"claim_text": "Acme is the market leader in 40 countries", "supported": False,
         "reason": "no chunk or system fact mentions market leadership", "confidence": 0.9},
    ])
    with patch("app.agents.explanation.call_llm", mock):
        verifications, score = await verify_narrative_claims(narr, {"c1": "..."})
    assert score == 0.5
    assert any(not v.supported for v in verifications)


async def test_low_confidence_supported_counts_as_unsupported():
    # A 'supported' verdict below confidence_floor (default 0.7) is NOT trusted —
    # bias toward flagging so the critic can route to human review.
    narr = _narr()
    mock = _mock_llm([
        {"claim_text": "Acme commits to 99.9% uptime", "supported": True,
         "supporting_chunk_id": "c1", "confidence": 0.4},
    ])
    with patch("app.agents.explanation.call_llm", mock):
        _, score = await verify_narrative_claims(narr, {"c1": "..."})
    assert score == 0.0


async def test_disabled_skips_llm(monkeypatch):
    monkeypatch.setattr(settings.platform.synthesis_verification, "enabled", False)
    narr = _narr()
    mock = _mock_llm([])
    with patch("app.agents.explanation.call_llm", mock):
        verifications, score = await verify_narrative_claims(narr, {"c1": "..."})
    assert (verifications, score) == ([], 1.0)
    mock.assert_not_awaited()


async def test_empty_prose_skips_llm():
    narr = _narr(prose="")
    mock = _mock_llm([])
    with patch("app.agents.explanation.call_llm", mock):
        verifications, score = await verify_narrative_claims(narr, {"c1": "..."})
    assert (verifications, score) == ([], 1.0)
    mock.assert_not_awaited()


async def test_unparseable_llm_is_vacuous_pass():
    narr = _narr()
    mock = AsyncMock(return_value="not json at all")
    with patch("app.agents.explanation.call_llm", mock):
        verifications, score = await verify_narrative_claims(narr, {"c1": "..."})
    assert (verifications, score) == ([], 1.0)


# ── critic_after_explanation — HARD/SOFT prose bands ─────────────────────────

def _verif(supported: bool, text="claim"):
    from app.schemas.output_models import ClaimVerification
    return ClaimVerification(claim_text=text, supported=supported)


def test_critic_hard_blocks_low_prose_score():
    # score 0.5 < block_below (0.7) → HARD
    narr = _narr(
        prose_verification=[_verif(True), _verif(False, "Acme is market leader")],
        prose_score=0.5,
    )
    out = critic_after_explanation(_exp([narr]), {"c1": "..."})
    assert "unsupported_prose_claims" in _flags(out, CriticSeverity.HARD)


def test_critic_soft_warns_mid_prose_score():
    # score 0.85: warn_below (0.9) > 0.85 >= block_below (0.7) → SOFT
    narr = _narr(
        prose_verification=[_verif(True), _verif(True), _verif(True), _verif(True),
                            _verif(True), _verif(True), _verif(False)],
        prose_score=0.857,
    )
    out = critic_after_explanation(_exp([narr]), {"c1": "..."})
    assert "weak_prose_support" in _flags(out, CriticSeverity.SOFT)
    assert "unsupported_prose_claims" not in _flags(out, CriticSeverity.HARD)


def test_critic_no_prose_flag_when_vacuous():
    # No prose_verification entries (disabled / nothing to check) → score 1.0,
    # must NOT trip either band.
    narr = _narr(prose_verification=[], prose_score=1.0)
    out = critic_after_explanation(_exp([narr]), {"c1": "..."})
    assert "unsupported_prose_claims" not in _flags(out, CriticSeverity.HARD)
    assert "weak_prose_support" not in _flags(out, CriticSeverity.SOFT)


def test_critic_no_prose_flag_when_disabled(monkeypatch):
    monkeypatch.setattr(settings.platform.synthesis_verification, "enabled", False)
    # Even with a low score present, a disabled pass raises no prose flag.
    narr = _narr(prose_verification=[_verif(False)], prose_score=0.0)
    out = critic_after_explanation(_exp([narr]), {"c1": "..."})
    assert "unsupported_prose_claims" not in _flags(out, CriticSeverity.HARD)
