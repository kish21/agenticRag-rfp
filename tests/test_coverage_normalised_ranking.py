"""
E3.d — coverage-normalised ranking.

A scoring criterion that could not be assessed (insufficient_evidence) contributes
0 to total_weighted_score — indistinguishable from a genuine 0/10. That under-ranks a
vendor that simply wasn't fully assessed. The evaluation agent now also emits `coverage`
(fraction of criterion-weight assessed) and `coverage_normalised_score` (quality over the
assessed weight, 0–10); the comparator ranks by the normalised score and flags vendors
below the configured coverage floor for human review.

CI-safe: the evaluation path here uses only no-evidence criteria (returns before any LLM
call); the comparator's per-criterion LLM call is monkeypatched.
"""
from __future__ import annotations

import asyncio

import pytest

from app.agents.evaluation import run_evaluation_agent
from app.agents import comparator as comparator_mod
from app.agents.comparator import run_comparator_agent
from app.config import settings
from app.schemas.output_models import (
    CriterionScore,
    EvaluationOutput,
    EvaluationSetup,
    ScoringCriterion,
)


# ── helpers ──────────────────────────────────────────────────────────────────
def _criterion(cid: str, weight: float, target: str) -> ScoringCriterion:
    return ScoringCriterion(
        criterion_id=cid, name=cid, weight=weight, extraction_target_ids=[target],
        rubric_9_10="Strong.", rubric_6_8="Reasonable.",
        rubric_3_5="Weak.", rubric_0_2="None.",
    )


def _score(cid: str, vid: str, raw: int, weight: float, insufficient: bool) -> CriterionScore:
    return CriterionScore(
        criterion_id=cid, vendor_id=vid,
        raw_score=0 if insufficient else raw,
        weighted_contribution=0.0 if insufficient else round((raw / 10) * weight, 4),
        confidence=0.0 if insufficient else 0.8,
        rubric_band_applied="insufficient_evidence" if insufficient else "9-10",
        evidence_used=[] if insufficient else ["q"],
        score_rationale="", variance_estimate=0.0,
        insufficient_evidence=insufficient,
    )


def _eval_output(vid: str, scores: list[CriterionScore], setup: EvaluationSetup) -> EvaluationOutput:
    """Build an EvaluationOutput the way the agent does, so coverage maths is exercised."""
    weight_by = {c.criterion_id: c.weight for c in setup.scoring_criteria}
    total_w = sum(weight_by.values())
    assessed_w = sum(weight_by[s.criterion_id] for s in scores if not s.insufficient_evidence)
    total_score = round(sum(s.weighted_contribution for s in scores) * 10, 2)
    coverage = round(assessed_w / total_w, 4) if total_w else 0.0
    normalised = round(total_score / coverage, 2) if coverage else 0.0
    return EvaluationOutput(
        evaluation_id=f"e-{vid}", vendor_id=vid, compliance_decisions=[],
        criterion_scores=scores, overall_compliance="pass",
        total_weighted_score=total_score, coverage=coverage,
        coverage_normalised_score=normalised, score_confidence=0.8,
    )


def _setup(criteria: list[ScoringCriterion]) -> EvaluationSetup:
    return EvaluationSetup(
        setup_id="s", org_id="o", department="it", rfp_id="r", rfp_confirmed=True,
        mandatory_checks=[], scoring_criteria=criteria,
        extraction_targets=[], total_weight=round(sum(c.weight for c in criteria), 4),
        confirmed_by="t", source="manually_defined",
    )


# ── exit criterion 1: coverage maths ─────────────────────────────────────────
def test_coverage_maths_partial_assessment():
    setup = _setup([_criterion("c1", 0.6, "t1"), _criterion("c2", 0.4, "t2")])
    # 10/10 on the 0.6-weight criterion; the 0.4-weight one is insufficient.
    scores = [_score("c1", "v", 10, 0.6, False), _score("c2", "v", 0, 0.4, True)]
    ev = _eval_output("v", scores, setup)
    assert ev.total_weighted_score == 6.0          # absolute view unchanged
    assert ev.coverage == 0.6
    assert ev.coverage_normalised_score == 10.0     # perfect over what was assessed


# ── exit criterion 2: no-change invariant at full coverage ───────────────────
def test_full_coverage_normalised_equals_total():
    setup = _setup([_criterion("c1", 0.5, "t1"), _criterion("c2", 0.5, "t2")])
    scores = [_score("c1", "v", 7, 0.5, False), _score("c2", "v", 6, 0.5, False)]
    ev = _eval_output("v", scores, setup)
    assert ev.coverage == 1.0
    assert ev.coverage_normalised_score == ev.total_weighted_score == 6.5


def test_backcompat_old_payload_normalised_falls_back_to_total():
    # Old-style construction (only total_weighted_score) must not default to 0.0/marginal.
    ev = EvaluationOutput(
        evaluation_id="e", vendor_id="v", compliance_decisions=[], criterion_scores=[],
        overall_compliance="pass", total_weighted_score=8.0, score_confidence=0.9,
    )
    assert ev.coverage == 1.0
    assert ev.coverage_normalised_score == 8.0


# ── exit criteria 3 + 4: ranking fix + low-coverage flag ─────────────────────
def _run_comparator(evals: dict[str, EvaluationOutput], setup: EvaluationSetup, monkeypatch):
    async def _fake_llm(*a, **k):
        return '{"vendor_differentiators": {}, "distinguishing_factors": "", "comparison_confidence": 0.7}'
    monkeypatch.setattr(comparator_mod, "call_llm", _fake_llm)
    out, _critic = asyncio.run(
        run_comparator_agent(list(evals), "o", "r", setup, evals)
    )
    return out


def test_partial_excellent_outranks_full_mediocre(monkeypatch):
    setup = _setup([_criterion("c1", 0.6, "t1"), _criterion("c2", 0.4, "t2")])
    # partial-but-excellent: cov 0.6, normalised 10.0, absolute 6.0
    partial = _eval_output(
        "partial",
        [_score("c1", "partial", 10, 0.6, False), _score("c2", "partial", 0, 0.4, True)],
        setup,
    )
    # full-but-mediocre: cov 1.0, normalised 6.5, absolute 6.5
    full = _eval_output(
        "full",
        [_score("c1", "full", 6, 0.6, False), _score("c2", "full", 7, 0.4, False)],
        setup,
    )
    out = _run_comparator({"partial": partial, "full": full}, setup, monkeypatch)
    # Absolute totals would rank full (6.5) above partial (6.0); normalised flips it.
    assert out.overall_ranking[0] == "partial"
    assert out.overall_ranking == ["partial", "full"]


def test_low_coverage_vendor_is_flagged(monkeypatch):
    setup = _setup([_criterion("c1", 0.3, "t1"), _criterion("c2", 0.7, "t2")])
    # assessed only the 0.3-weight criterion → coverage 0.3 < 0.5 floor
    sliver = _eval_output(
        "sliver",
        [_score("c1", "sliver", 10, 0.3, False), _score("c2", "sliver", 0, 0.7, True)],
        setup,
    )
    well = _eval_output(
        "well",
        [_score("c1", "well", 8, 0.3, False), _score("c2", "well", 8, 0.7, False)],
        setup,
    )
    assert sliver.coverage < settings.platform.ranking.min_coverage_for_trust
    out = _run_comparator({"sliver": sliver, "well": well}, setup, monkeypatch)
    assert "sliver" in out.low_coverage_vendors
    assert "well" not in out.low_coverage_vendors
    assert any("sliver" in w and "human review" in w for w in out.comparison_warnings)


# ── exit criterion 5: config-driven ──────────────────────────────────────────
def test_min_coverage_floor_is_config_driven(monkeypatch):
    setup = _setup([_criterion("c1", 0.4, "t1"), _criterion("c2", 0.6, "t2")])
    v = _eval_output(
        "v",
        [_score("c1", "v", 9, 0.4, False), _score("c2", "v", 0, 0.6, True)],  # coverage 0.4
        setup,
    )
    # Floor 0.3 → not flagged; floor 0.5 → flagged. Same vendor, only config changes.
    monkeypatch.setattr(settings.platform.ranking, "min_coverage_for_trust", 0.3)
    out_low = _run_comparator({"v": v}, setup, monkeypatch)
    assert out_low.low_coverage_vendors == []

    monkeypatch.setattr(settings.platform.ranking, "min_coverage_for_trust", 0.5)
    out_high = _run_comparator({"v": v}, setup, monkeypatch)
    assert out_high.low_coverage_vendors == ["v"]


# ── evaluation agent end-to-end (no-evidence path, no LLM) ───────────────────
def test_evaluation_agent_emits_coverage(monkeypatch):
    import app.agents.evaluation as ev_mod

    async def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("no-evidence path must not call the LLM")
    monkeypatch.setattr(ev_mod, "call_llm", _boom)
    # No PostgreSQL facts → every criterion insufficient → coverage 0.0 (no LLM, CI-safe)
    monkeypatch.setattr(ev_mod, "get_vendor_facts", lambda *a, **k: {})

    setup = _setup([_criterion("c1", 0.5, "t1"), _criterion("c2", 0.5, "t2")])
    out, _critic = asyncio.run(
        run_evaluation_agent(vendor_id="v", org_id="o", evaluation_setup=setup)
    )
    assert out.coverage == 0.0
    assert out.coverage_normalised_score == 0.0
    assert out.total_weighted_score == 0.0
