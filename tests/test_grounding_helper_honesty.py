"""
P2.25 + P2.26 — shared grounding helper + claim-free honesty gate.

P2.25: `compute_grounding` is the single source of truth for grounding
completeness + base limitations. The live graph (`app/pipeline/nodes.py
::explanation_finalise`) and the legacy single-call path
(`app/agents/explanation.py::run_explanation_agent`) both call it, instead of
each carrying a byte-identical inline copy that could silently diverge.

P2.26: a claim-free report computes a *vacuous* grounding_completeness of 1.0
(nothing to ground != 100% verified). The critic must surface that as a SOFT
`claim_free_report` flag so it still gets human eyes, rather than letting the
vacuous 1.0 pass silently through the numeric honesty gate.
"""
import inspect

from app.agents.critic import critic_after_explanation
from app.agents.explanation import compute_grounding
from app.schemas.output_models import (
    ExplanationOutput, VendorNarrative, GroundedClaim, SystemFact, CriticSeverity,
)


# ── helpers ─────────────────────────────────────────────────────────────────

def _claim(text: str = "Acme holds ISO 27001.") -> GroundedClaim:
    return GroundedClaim(
        claim_text=text, grounding_quote=text, source_chunk_id="c1",
    )


def _narr(vendor_id, grounded=0, removed=0, system_facts=None) -> VendorNarrative:
    return VendorNarrative(
        vendor_id=vendor_id, vendor_name=vendor_id, executive_summary="",
        compliance_narrative="", scoring_narrative="", recommendation_rationale="",
        grounded_claims=[_claim() for _ in range(grounded)],
        ungrounded_claims_removed=removed,
        system_facts=system_facts or [],
    )


def _exp(narratives) -> ExplanationOutput:
    completeness, _, _ = compute_grounding(narratives)
    return ExplanationOutput(
        explanation_id="x", executive_summary="", vendor_narratives=narratives,
        methodology_note="", grounding_completeness=completeness, report_confidence=0.8,
    )


def _flags(critic_out, severity):
    return {f.check_name for f in critic_out.flags if f.severity == severity}


# ── P2.25 — compute_grounding correctness ─────────────────────────────────────

def test_compute_grounding_all_grounded_is_one():
    completeness, total, lims = compute_grounding([_narr("a", grounded=3)])
    assert completeness == 1.0
    assert total == 3
    assert lims == []  # nothing to flag — every claim grounded


def test_compute_grounding_partial_fraction():
    # 2 grounded of 4 attempted (2 removed) → 0.5, rounded to 3dp.
    completeness, total, lims = compute_grounding([_narr("a", grounded=2, removed=2)])
    assert completeness == 0.5
    assert total == 4
    assert any("2 unverified claim(s) removed" in m for m in lims)


def test_compute_grounding_system_fact_only_is_vacuous_one_not_zero():
    # A vendor whose entire story is system_facts made no PDF claim → not scored 0%.
    narr = _narr("epsilon", system_facts=[
        SystemFact(fact_text="Rejected — PI insurance £10M vs £2M conflict.",
                   origin="evaluation", origin_id="chk-pi")])
    completeness, total, lims = compute_grounding([narr])
    assert completeness == 1.0       # vacuous — nothing needed grounding
    assert total == 0
    assert any("No grounded claims were produced" in m for m in lims)


def test_compute_grounding_excludes_claim_free_from_denominator():
    # One claim-bearing (all grounded) + one system-fact-only vendor → 1.0, the
    # claim-free vendor must not drag the fraction down.
    bearing = _narr("a", grounded=2)
    sysonly = _narr("b", system_facts=[
        SystemFact(fact_text="Rank 2.", origin="comparator")])
    completeness, total, _ = compute_grounding([bearing, sysonly])
    assert completeness == 1.0
    assert total == 2


def test_no_inline_grounding_duplication_in_live_path():
    """Drift guard for P2.25 — the live graph path must compute grounding via the
    shared helper, not re-introduce an inline `grounded_claims / total_claims`."""
    from app.pipeline import nodes
    src = inspect.getsource(nodes.explanation_finalise)
    assert "compute_grounding(" in src, "live path must call the shared helper"
    assert "grounded_claims / total_claims" not in src, "inline duplicate re-introduced"


# ── P2.26 — claim-free report SOFT honesty flag ───────────────────────────────

def test_claim_free_report_gets_soft_flag():
    # Every vendor's story is trusted system_facts (no PDF claim). The report ships
    # with grounding_completeness vacuously 1.0 — it must still be flagged SOFT.
    narr = _narr("epsilon", system_facts=[
        SystemFact(fact_text="Rejected — insurance conflict.",
                   origin="evaluation", origin_id="chk-pi")])
    out = _exp([narr])
    assert out.grounding_completeness == 1.0
    critic_out = critic_after_explanation(out, {})
    assert "claim_free_report" in _flags(critic_out, CriticSeverity.SOFT)
    # It is advisory, not blocking — the report still completes.
    assert "claim_free_report" not in _flags(critic_out, CriticSeverity.HARD)


def test_genuinely_grounded_report_has_no_claim_free_flag():
    # A report with real PDF-grounded claims is NOT claim-free.
    out = _exp([_narr("a", grounded=3)])
    assert out.grounding_completeness == 1.0
    critic_out = critic_after_explanation(out, {"c1": "Acme holds ISO 27001."})
    assert "claim_free_report" not in _flags(critic_out, CriticSeverity.SOFT)


def test_claim_free_flag_independent_of_empty_narrative_block():
    # A truly-empty vendor (no claims, none removed, no system_facts) still HARD
    # blocks as empty_narrative; the claim-free SOFT flag fires alongside it.
    out = _exp([_narr("ghost")])
    critic_out = critic_after_explanation(out, {})
    assert "empty_narrative" in _flags(critic_out, CriticSeverity.HARD)
    assert "claim_free_report" in _flags(critic_out, CriticSeverity.SOFT)
