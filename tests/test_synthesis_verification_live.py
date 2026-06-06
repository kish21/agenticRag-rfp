"""
P1.8 — LIVE true-positive proof for the synthesis verifier.

The unit tests (test_synthesis_verification.py) prove the plumbing downstream of
a "false" verdict with a MOCKED LLM, and the benchmark proves the verifier does
not false-positive on genuinely-grounded prose. This test closes the remaining
gap: does the REAL model + the verify_claims prompt actually FLAG a deliberately
planted, unsupported prose claim — and does that drive the Critic to HARD-block?

It calls the live LLM, so it runs ONLY when explicitly opted in with
``RUN_LIVE_LLM=1`` and a real OpenAI key. CI does NOT set RUN_LIVE_LLM (and seeds
a dummy key for other tests), so this is skipped there; run it locally with a
real key. It is intentionally the only live-LLM unit test; the benchmark is the
other live exercise.
"""
import os

import pytest

from app.config import settings
from app.agents.explanation import verify_narrative_claims
from app.agents.critic import critic_after_explanation
from app.schemas.output_models import (
    ExplanationOutput, VendorNarrative, GroundedClaim, CriticSeverity,
)

# Explicit opt-in only — presence of an API key is NOT a sufficient gate because
# CI injects a dummy key (sk-fake-…) for the rest of the suite, which would make
# a key-presence check run this test and 401.
pytestmark = pytest.mark.skipif(
    not (
        os.getenv("RUN_LIVE_LLM", "").lower() in ("1", "true", "yes")
        and settings.llm_provider == "openai"
        and settings.openai_api_key
    ),
    reason="live LLM test — set RUN_LIVE_LLM=1 with a real OPENAI_API_KEY to run",
)


# The ONLY evidence the writer had: one chunk about uptime. Nothing here mentions
# ISO 27001, an employee count, or any named client — so any prose asserting
# those is a fabrication the verifier must catch.
SOURCE_CHUNKS = {
    "acme-c1": "Acme guarantees 99.9% platform uptime measured monthly, "
               "with service credits for any shortfall below that threshold.",
}


def _narrative_with_planted_hallucination() -> VendorNarrative:
    return VendorNarrative(
        vendor_id="acme",
        vendor_name="Acme",
        # 1 supported sentence (uptime, in the chunk) + 2 fabrications (a
        # certification and a client/headcount claim) absent from all evidence.
        executive_summary=(
            "Acme guarantees 99.9% platform uptime. Acme is ISO 27001 certified "
            "and has delivered identical platforms for the Bank of England."
        ),
        compliance_narrative="Acme employs 4,000 engineers across 30 countries.",
        scoring_narrative="",
        recommendation_rationale="",
        # The uptime claim is legitimately grounded — give the verifier the same
        # verified-claim context the real pipeline would.
        grounded_claims=[GroundedClaim(
            claim_text="Acme guarantees 99.9% platform uptime.",
            grounding_quote="Acme guarantees 99.9% platform uptime",
            source_chunk_id="acme-c1",
        )],
    )


async def test_live_verifier_flags_planted_hallucination_and_critic_blocks():
    narr = _narrative_with_planted_hallucination()

    verifications, score = await verify_narrative_claims(narr, SOURCE_CHUNKS)

    # The model must have produced per-claim verdicts and flagged at least one
    # fabrication — i.e. it discriminates, not just passes everything.
    assert verifications, "verifier returned no claim verdicts on live call"
    unsupported = [v for v in verifications if not v.supported]
    assert unsupported, (
        "live verifier failed to flag any unsupported prose claim — "
        f"verdicts={[(v.claim_text, v.supported) for v in verifications]}"
    )
    # Partial support → score strictly below 1.0 and below the block threshold,
    # since 2 of ~3 factual claims are fabricated.
    assert score < settings.platform.synthesis_verification.block_below, (
        f"expected score < block_below; got {score}"
    )

    # flags -> HARD block: feed the verified narrative through the real critic.
    narr.prose_verification = verifications
    narr.prose_verification_score = score
    out = ExplanationOutput(
        explanation_id="live", executive_summary="", vendor_narratives=[narr],
        methodology_note="", grounding_completeness=1.0, report_confidence=0.8,
    )
    critic = critic_after_explanation(out, SOURCE_CHUNKS)
    hard = {f.check_name for f in critic.flags if f.severity == CriticSeverity.HARD}
    assert "unsupported_prose_claims" in hard, (
        f"critic did not HARD-block on unsupported prose; flags={hard}"
    )
