"""
Issue #212 — reranker air-gapped default.

Before this work, a brand-new org (no org_settings row) resolved its reranker
backend from the product.yaml quality preset, which hardcoded `bge`. That
OVERRODE the operator's .env RERANKER_PROVIDER and forced a local HuggingFace
download — in an air-gapped VPC that silently degraded retrieval to vector-score
order with no operator signal.

These tests pin the two properties of the fix:
  1. The backend is a DEPLOYMENT choice, sourced from .env (single source of
     truth). The preset no longer pins it, so a tier change cannot reset it.
  2. Fail-open but LOUD: when a real reranker is unavailable and retrieval falls
     back to vector order, that degradation is surfaced (warning + critic flag),
     never silent. `none` is an intentional choice and is NOT reported.

All tests are pure (no DB / no network / no external API).
"""
import pytest

import app.config as ac
from app.config import settings as cfg
from app.domain.org_settings import _defaults_for
from app.providers.reranker import rerank
from app.schemas.schema_ingestion_retrieval import RetrievalOutput, RetrievedChunk
from app.schemas.schema_planner_critic import CriticSeverity
from app.agents.critic import critic_after_retrieval


_CANDS = [
    {"text": "alpha", "score": 0.9, "payload": {}},
    {"text": "beta", "score": 0.4, "payload": {}},
]


# ── 1. Backend is sourced from .env, single source of truth ──────────────────

def test_defaulted_org_follows_env_provider(monkeypatch):
    """A defaulted org resolves reranker_provider from .env, not a hardcoded bge.

    Flip the .env-derived value and the resolved default must follow — across
    every supported provider, with no code change."""
    for provider in ("bge", "modal", "cohere", "none"):
        monkeypatch.setattr(ac.settings, "reranker_provider", provider)
        resolved = _defaults_for("acme-org").reranker_provider
        assert resolved == provider, (
            f".env RERANKER_PROVIDER={provider} must drive the defaulted org, "
            f"got {resolved!r}"
        )


def test_preset_does_not_pin_reranker_backend():
    """The quality presets must NOT carry reranker_provider — pinning it there is
    exactly what made .env dead config and silently reset the backend on a tier
    change. The preset governs WHETHER to rerank (use_reranking), not WHICH
    backend serves it."""
    for tier, preset in cfg.product.presets.items():
        assert "reranker_provider" not in preset.config, (
            f"preset {tier!r} must not pin reranker_provider — backend comes "
            f"from .env via _defaults_for"
        )
        # the product-quality decision (whether to rerank) stays in the preset
        assert "use_reranking" in preset.config


# ── 2. Fail-open but LOUD ────────────────────────────────────────────────────

def test_unavailable_reranker_reports_degradation():
    """An unknown/unavailable real provider falls back to vector order AND
    appends an operator-facing degradation warning to the passed list."""
    warnings: list[str] = []
    out = rerank("q", [dict(c) for c in _CANDS], top_n=2,
                 provider="bogus-provider", warnings=warnings)
    assert warnings, "a non-'none' fallback must surface a degradation warning"
    assert "fell back to vector-score order" in warnings[0]
    # vector-score order means the highest raw score is first
    assert out[0]["rerank_score"] == 0.9


def test_none_provider_is_not_reported_as_degraded():
    """`none` is an intentional 'do not rerank' choice — never a degradation."""
    warnings: list[str] = []
    rerank("q", [dict(c) for c in _CANDS], top_n=2,
           provider="none", warnings=warnings)
    assert warnings == []


def test_critic_flags_reranking_degraded_soft():
    """When retrieval reports reranking_degraded, the critic raises a SOFT flag
    so an operator sees the silent-degrade — but does not HARD-block the run
    (fail-open: results are still usable, just not reranked)."""
    out = RetrievalOutput(
        query_id="x", original_query="q", rewritten_query="q",
        hyde_query_used=False, retrieval_strategy="hybrid+rerank",
        chunks=[], total_candidates_before_rerank=2, confidence=0.5,
        empty_retrieval=False, reranking_degraded=True,
        warnings=["Reranking degraded: provider 'bge' is unavailable (...)"],
    )
    critic = critic_after_retrieval(out)
    degraded = [f for f in critic.flags if f.check_name == "reranking_degraded"]
    assert len(degraded) == 1
    assert degraded[0].severity == CriticSeverity.SOFT


def test_no_degraded_flag_when_reranking_ok():
    """A healthy retrieval (reranking_degraded=False) raises no degraded flag."""
    out = RetrievalOutput(
        query_id="x", original_query="q", rewritten_query="q",
        hyde_query_used=False, retrieval_strategy="hybrid+rerank",
        chunks=[], total_candidates_before_rerank=2, confidence=0.5,
        empty_retrieval=False, reranking_degraded=False, warnings=[],
    )
    critic = critic_after_retrieval(out)
    assert not [f for f in critic.flags if f.check_name == "reranking_degraded"]


def test_degraded_confidence_factor_is_config_driven():
    """The confidence penalty applied on degrade must come from config, not be
    hardcoded (CLAUDE.md: no hardcoded thresholds)."""
    factor = cfg.platform.retrieval.rerank_degraded_confidence_factor
    assert 0.0 < factor <= 1.0


# ── 3. Live graph path must NOT drop the signal (regression guard) ───────────

@pytest.mark.asyncio
async def test_live_node_propagates_degradation_into_combined_output(monkeypatch):
    """The multi-query merge in retrieval_per_vendor (nodes.py) rebuilds a
    `combined` RetrievalOutput. It MUST carry the per-query reranking_degraded
    signal + warnings into that combined output and apply the confidence penalty
    — otherwise the air-gapped degradation is silent in the live graph (the exact
    regression the #212 review caught)."""
    from app.pipeline import nodes
    from app.schemas.schema_planner_critic import (
        CriticOutput, CriticVerdict,
    )

    chunk = RetrievedChunk(
        chunk_id="c1", qdrant_point_id="c1", text="alpha", section_id="s1",
        section_title="S", section_type="requirement_response", filename="v.pdf",
        page_number=1, vendor_id="v1", vector_similarity_score=0.9,
        rerank_score=0.9, final_score=0.9, is_answer_bearing=True,
    )
    degraded_out = RetrievalOutput(
        query_id="q1", original_query="q", rewritten_query="q",
        hyde_query_used=False, retrieval_strategy="hybrid", chunks=[chunk],
        total_candidates_before_rerank=1, confidence=0.72, empty_retrieval=False,
        reranking_degraded=True,
        warnings=["Reranking degraded: provider 'modal' is unavailable (...)"],
    )
    approved = CriticOutput(
        critic_run_id="cr", evaluated_agent="retrieval_agent",
        evaluated_output_id="q1", overall_verdict=CriticVerdict.APPROVED, flags=[],
    )

    async def fake_run_retrieval_agent(**kwargs):
        return degraded_out, approved

    monkeypatch.setattr(nodes, "run_retrieval_agent", fake_run_retrieval_agent)

    state = {
        "run_id": "r1", "org_id": "o1", "rfp_id": "rfp1", "vendor_id": "v1",
        "org_settings": None,
        "evaluation_setup_dict": {
            "setup_id": "s", "org_id": "o1", "department": "IT", "rfp_id": "rfp1",
            "rfp_confirmed": True, "mandatory_checks": [], "scoring_criteria": [],
            "extraction_targets": [], "total_weight": 1.0, "confirmed_by": "t",
            "confirmed_at": None, "source": "csv",
        },
    }

    result = await nodes.retrieval_per_vendor(state)

    combined = result["retrieval_output_objects"]["v1"]
    assert combined.reranking_degraded is True, "degradation dropped in live path"
    assert combined.warnings, "warnings dropped in live path"
    factor = cfg.platform.retrieval.rerank_degraded_confidence_factor
    assert combined.confidence == round(0.9 * factor, 3), "penalty not applied"
