"""
E3 Stage 4 — no forced scores (exit criteria D1/D2).

When a scoring criterion has no evidence, the evaluation agent must NOT call the
LLM to invent a score: it returns a CriterionScore flagged insufficient_evidence
with raw_score 0 and zero weighted contribution. CI-safe — the no-evidence path
returns before any LLM call, so no network/key is needed.
"""
from __future__ import annotations

import asyncio

from app.agents.evaluation import _score_criterion
from app.schemas.output_models import ScoringCriterion


def _criterion() -> ScoringCriterion:
    return ScoringCriterion(
        criterion_id="crit-sla", name="Service-level commitments", weight=0.30,
        extraction_target_ids=["ext-sla"],
        rubric_9_10="Strong SLAs.", rubric_6_8="Reasonable SLAs.",
        rubric_3_5="Weak SLAs.", rubric_0_2="No SLAs.",
    )


def test_no_evidence_yields_insufficient_not_forced_zero(monkeypatch):
    # Guard: if the no-evidence path ever calls the LLM, fail loudly.
    import app.agents.evaluation as ev

    async def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("LLM must NOT be called when there is no evidence")
    monkeypatch.setattr(ev, "call_llm", _boom)

    score = asyncio.run(_score_criterion(_criterion(), [], vendor_id="v1"))

    assert score.insufficient_evidence is True
    assert score.raw_score == 0
    assert score.weighted_contribution == 0.0
    assert score.confidence == 0.0
    assert score.rubric_band_applied == "insufficient_evidence"
    assert score.evidence_used == []


def test_criterion_score_defaults_insufficient_false():
    from app.schemas.output_models import CriterionScore
    cs = CriterionScore(criterion_id="c", vendor_id="v", raw_score=7,
                        weighted_contribution=0.21, confidence=0.8,
                        rubric_band_applied="6-8", evidence_used=["q"],
                        score_rationale="ok", variance_estimate=0.5)
    assert cs.insufficient_evidence is False     # backward-compatible default
