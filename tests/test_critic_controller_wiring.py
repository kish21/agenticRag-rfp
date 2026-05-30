"""
Phase 2c — wiring tests for the Critic-as-controller at the generation steps.

The engine (run_with_critic_retry) is covered by tests/test_critic_retry.py.
This file proves the *wiring* added on top of it:

  W1 — _merge_critic_metrics deep-merges per-vendor telemetry across the two
       stages (extraction then evaluation for the SAME vendor) without clobber.
       This is the exact P2.0c code-review gap.
  W2 — run_extraction_agent prepends the 'PREVIOUS ATTEMPT FAILED' preamble to
       its LLM prompt only when critic_feedback is non-empty.
  W3 — run_evaluation_agent threads critic_feedback into both the mandatory-check
       and criterion-scoring prompts.
  W4 — extraction_per_vendor routes through the controller: a HARD verdict then
       an OK verdict yields a recovered success + critic_metrics_accum telemetry,
       and the corrective feedback reaches the agent on the retry.
  W5 — evaluation_per_vendor exhausts to failed_vendors with telemetry (the
       Phase-4 HARD-block guard is preserved through the controller).
  W6 — _summarise_critic_metrics rolls the per-vendor map up by agent.

Offline: no real LLM, no Postgres, no Qdrant.

Run:
    python -m pytest tests/test_critic_controller_wiring.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipeline.state import _merge_critic_metrics  # noqa: E402
from app.schemas.schema_enums import CriticVerdict  # noqa: E402

_OK = next(v for v in CriticVerdict if v != CriticVerdict.BLOCKED)


# ── W1 — reducer deep-merges across stages (the P2.0c gap) ───────────────────

def test_merge_critic_metrics_keeps_both_stages_same_vendor():
    """extraction writes {v1:{extraction:..}} in one stage; evaluation writes
    {v1:{evaluation:..}} in a LATER stage. A shallow update() would drop the
    extraction bucket — the deep reducer must keep both."""
    left = {"v1": {"extraction": {"blocks": 1, "retry_success": True}}}
    right = {"v1": {"evaluation": {"blocks": 0, "retry_success": False}}}
    merged = _merge_critic_metrics(left, right)
    assert set(merged["v1"]) == {"extraction", "evaluation"}
    assert merged["v1"]["extraction"]["blocks"] == 1
    assert merged["v1"]["evaluation"]["blocks"] == 0


def test_merge_critic_metrics_parallel_distinct_vendors():
    """Within one stage's fan-out the vendor_ids are distinct — straightforward
    merge, no collision."""
    left = {"acme": {"extraction": {"blocks": 0}}}
    right = {"apex": {"extraction": {"blocks": 2}}}
    merged = _merge_critic_metrics(left, right)
    assert merged == {
        "acme": {"extraction": {"blocks": 0}},
        "apex": {"extraction": {"blocks": 2}},
    }


def test_merge_critic_metrics_handles_none():
    assert _merge_critic_metrics(None, {"v": {"e": {}}}) == {"v": {"e": {}}}
    assert _merge_critic_metrics({"v": {"e": {}}}, None) == {"v": {"e": {}}}
    # left is not mutated
    left = {"v": {"e": {"blocks": 1}}}
    _merge_critic_metrics(left, {"v": {"x": {}}})
    assert left == {"v": {"e": {"blocks": 1}}}


# ── W2 — extraction agent injects the feedback preamble ──────────────────────

def _retrieval_output_with_chunk():
    from app.schemas.output_models import RetrievalOutput
    from app.schemas.schema_ingestion_retrieval import RetrievedChunk
    chunk = RetrievedChunk(
        chunk_id="c1", qdrant_point_id="p1", text="ISO 27001 certified since 2019.",
        section_id="s1", section_title="Security", section_type="requirement_response",
        filename="acme.pdf", page_number=1, vendor_id="acme",
        vector_similarity_score=0.9, rerank_score=0.9, final_score=0.9,
        is_answer_bearing=True,
    )
    return RetrievalOutput(
        query_id="q1", original_query="certs", rewritten_query="certs",
        hyde_query_used=False, retrieval_strategy="dense", chunks=[chunk],
        total_candidates_before_rerank=1, confidence=0.9, empty_retrieval=False,
    )


def _eval_setup():
    from app.schemas.output_models import EvaluationSetup
    return EvaluationSetup(
        setup_id="s1", org_id="", department="proc", rfp_id="r1", rfp_confirmed=True,
        mandatory_checks=[], scoring_criteria=[], extraction_targets=[],
        total_weight=1.0, confirmed_by="a@b", source="manually_defined",
    )


def _empty_setup_dict():
    return {
        "setup_id": "s1", "org_id": "", "department": "proc", "rfp_id": "rfp1",
        "rfp_confirmed": True, "scoring_criteria": [], "mandatory_checks": [],
        "extraction_targets": [], "total_weight": 1.0, "confirmed_by": "a@b",
        "source": "manually_defined",
    }


@pytest.mark.asyncio
async def test_extraction_injects_feedback_only_when_present():
    from app.agents import extraction as ext_mod

    captured: list[list[dict]] = []

    async def fake_call_llm(messages, **kwargs):
        captured.append(messages)
        return "{}"

    ro = _retrieval_output_with_chunk()
    setup = _eval_setup()

    with patch.object(ext_mod, "call_llm", fake_call_llm), \
         patch.object(ext_mod, "save_extraction_output"):
        # org_id="" skips the inner extraction-critic retry loop and DB read,
        # isolating the prompt-construction path under test.
        await ext_mod.run_extraction_agent(
            retrieval_output=ro, vendor_id="acme", org_id="",
            doc_id="d1", setup_id="s1", evaluation_setup=setup,
            critic_feedback="",
        )
        await ext_mod.run_extraction_agent(
            retrieval_output=ro, vendor_id="acme", org_id="",
            doc_id="d1", setup_id="s1", evaluation_setup=setup,
            critic_feedback="PREVIOUS ATTEMPT FAILED: fix the ISO quote.",
        )

    first_user = captured[0][1]["content"]
    second_user = captured[1][1]["content"]
    assert "PREVIOUS ATTEMPT FAILED" not in first_user
    assert "PREVIOUS ATTEMPT FAILED: fix the ISO quote." in second_user
    # the document context is still present after the preamble
    assert "ISO 27001 certified" in second_user


# ── W3 — evaluation agent threads feedback into its prompts ──────────────────

@pytest.mark.asyncio
async def test_evaluation_injects_feedback_into_prompts():
    from app.agents import evaluation as ev_mod
    from app.schemas.output_models import (
        EvaluationSetup, MandatoryCheck, ScoringCriterion, ExtractionTarget,
    )

    target = ExtractionTarget(
        target_id="t1", name="Certifications", description="ISO certs",
        fact_type="certification", is_mandatory=True,
    )
    check = MandatoryCheck(
        check_id="m1", name="ISO 27001", description="Must hold ISO 27001",
        what_passes="Holds a current ISO 27001 certificate",
        extraction_target_id="t1",
    )
    criterion = ScoringCriterion(
        criterion_id="cr1", name="Security maturity", weight=1.0,
        rubric_9_10="excellent", rubric_6_8="good", rubric_3_5="fair",
        rubric_0_2="poor", extraction_target_ids=["t1"],
    )
    setup = EvaluationSetup(
        setup_id="s1", org_id="", department="proc", rfp_id="r1", rfp_confirmed=True,
        mandatory_checks=[check], scoring_criteria=[criterion],
        extraction_targets=[target], total_weight=1.0,
        confirmed_by="a@b", source="manually_defined",
    )

    captured: list[list[dict]] = []

    async def fake_call_llm(messages, **kwargs):
        captured.append(messages)
        # valid-enough JSON for both prompt types
        return ('{"decision":"pass","confidence":0.9,"reasoning":"ok",'
                '"evidence_used":["ISO 27001"],"contradictions_found":[],'
                '"decision_basis":"explicit_confirmation",'
                '"raw_score":8,"rubric_band_applied":"6-8","score_rationale":"ok",'
                '"variance_estimate":0.5}')

    with patch.object(ev_mod, "call_llm", fake_call_llm), \
         patch.object(ev_mod, "get_vendor_facts", return_value={
             "certifications": [{"name": "ISO 27001", "grounding_quote": "ISO 27001"}],
             "insurance": [], "slas": [], "projects": [], "pricing": [],
             "extracted_facts": [],
         }):
        await ev_mod.run_evaluation_agent(
            vendor_id="acme", org_id="", evaluation_setup=setup,
            critic_feedback="PREVIOUS ATTEMPT FAILED: be stricter on evidence.",
        )

    # Every captured prompt (mandatory-check + criterion) carries the preamble.
    assert captured, "no LLM calls captured"
    assert all(
        "PREVIOUS ATTEMPT FAILED: be stricter on evidence." in m[1]["content"]
        for m in captured
    )


# ── W4 — extraction_per_vendor routes through the controller ─────────────────

class _Sev:
    def __init__(self, value): self.value = value


class _Flag:
    def __init__(self, description):
        self.description = description
        self.severity = _Sev("hard")
        self.recommendation = "add the verbatim source quote"


class _Critic:
    def __init__(self, verdict, flags=None):
        self.overall_verdict = verdict
        self.flags = flags or []


def _ext_state(vid="acme"):
    return {
        "org_id": "org1", "rfp_id": "rfp1", "vendor_id": vid, "setup_id": "s1",
        "run_id": "run1",
        "evaluation_setup_dict": _empty_setup_dict(),
        "retrieval_output_objects": {vid: object()},
    }


@pytest.mark.asyncio
async def test_extraction_per_vendor_recovers_after_block():
    from app.pipeline import nodes

    seq = {"i": 0}
    seen_feedback: list[str] = []

    async def fake_run_extraction(*, retrieval_output, vendor_id, org_id, doc_id,
                                  setup_id, evaluation_setup, run_id="",
                                  critic_feedback=""):
        seen_feedback.append(critic_feedback)
        i = seq["i"]; seq["i"] += 1
        out = type("O", (), {"slas": [], "pricing": [], "extracted_facts": [],
                             "extraction_completeness": 1.0, "hallucination_risk": 0.0})()
        if i == 0:
            return out, _Critic(CriticVerdict.BLOCKED, [_Flag("fact has no source quote")])
        return out, _Critic(_OK)

    with patch.object(nodes, "run_extraction_agent", fake_run_extraction), \
         patch.object(nodes, "_emit", lambda *a, **k: None), \
         patch("app.db.fact_store.facts_already_extracted", return_value=False):
        res = await nodes.extraction_per_vendor(_ext_state())

    assert "extraction_output_objects" in res and "failed_vendors" not in res
    m = res["critic_metrics_accum"]["acme"]["extraction"]
    assert m["blocks"] == 1 and m["retry_success"] is True and m["exhausted"] is False
    # retry carried the corrective feedback to the agent
    assert seen_feedback[0] == ""
    assert "PREVIOUS ATTEMPT FAILED" in seen_feedback[1]
    assert "no source quote" in seen_feedback[1]


# ── W5 — evaluation_per_vendor exhausts to failed_vendors (guard preserved) ──

@pytest.mark.asyncio
async def test_evaluation_per_vendor_exhausts_to_failed():
    from app.pipeline import nodes

    async def always_block(*, vendor_id, org_id, run_id, evaluation_setup,
                           extraction_output=None, critic_feedback=""):
        out = object()
        return out, _Critic(CriticVerdict.BLOCKED, [_Flag("score has no evidence")])

    state = {
        "org_id": "org1", "vendor_id": "acme", "run_id": "run1",
        "evaluation_setup_dict": _empty_setup_dict(),
        "extraction_output_objects": {"acme": object()},
    }

    with patch.object(nodes, "run_evaluation_agent", always_block), \
         patch.object(nodes, "_emit", lambda *a, **k: None):
        res = await nodes.evaluation_per_vendor(state)

    assert "evaluation_output_objects" not in res
    fv = res["failed_vendors"]
    assert len(fv) == 1 and fv[0]["vendor_id"] == "acme" and fv[0]["stage"] == "evaluation"
    assert "critic_hard_block after 3 attempts" in fv[0]["error"]
    m = res["critic_metrics_accum"]["acme"]["evaluation"]
    assert m["blocks"] == 3 and m["exhausted"] is True


@pytest.mark.asyncio
async def test_evaluation_per_vendor_recovers_after_block():
    """P1 symmetry — Evaluation self-corrects at the NODE level too (not only via
    the shared engine): a HARD verdict then OK yields a recovered success with
    telemetry, and the corrective feedback reaches the evaluation agent."""
    from app.pipeline import nodes

    seq = {"i": 0}
    seen_feedback: list[str] = []

    async def fake_run_evaluation(*, vendor_id, org_id, run_id, evaluation_setup,
                                  extraction_output=None, critic_feedback=""):
        seen_feedback.append(critic_feedback)
        i = seq["i"]; seq["i"] += 1
        out = object()
        if i == 0:
            return out, _Critic(CriticVerdict.BLOCKED, [_Flag("score has no evidence")])
        return out, _Critic(_OK)

    state = {
        "org_id": "org1", "vendor_id": "acme", "run_id": "run1",
        "evaluation_setup_dict": _empty_setup_dict(),
        "extraction_output_objects": {"acme": object()},
    }

    with patch.object(nodes, "run_evaluation_agent", fake_run_evaluation), \
         patch.object(nodes, "_emit", lambda *a, **k: None):
        res = await nodes.evaluation_per_vendor(state)

    assert "evaluation_output_objects" in res and "failed_vendors" not in res
    m = res["critic_metrics_accum"]["acme"]["evaluation"]
    assert m["blocks"] == 1 and m["retry_success"] is True and m["exhausted"] is False
    assert seen_feedback[0] == ""
    assert "PREVIOUS ATTEMPT FAILED" in seen_feedback[1]
    assert "no evidence" in seen_feedback[1]


def test_recovered_status_writes_audit_row():
    """C2 — a self-correction is recorded in the formal audit() table, not only
    the event_log timeline. _emit must map status='recovered' to an audit event."""
    from app.pipeline import nodes

    audit_calls: list[dict] = []
    state = {"run_id": "run1", "org_id": "org1"}

    with patch.object(nodes, "_db_append_event", lambda *a, **k: None), \
         patch.object(nodes, "_db_append_log", lambda *a, **k: None), \
         patch.object(nodes, "audit",
                      lambda **kw: audit_calls.append(kw)):
        nodes._emit(state, "extraction", "recovered",
                    "extraction for acme self-corrected after 1 retry",
                    log_msg="extraction for acme self-corrected after 1 retry")

    assert len(audit_calls) == 1
    assert audit_calls[0]["event_type"] == "agent.self_corrected"
    assert audit_calls[0]["agent"] == "extraction"
    assert "self-corrected" in audit_calls[0]["detail"]["message"]


@pytest.mark.asyncio
async def test_evaluation_per_vendor_skips_when_no_extraction():
    from app.pipeline import nodes
    state = {
        "org_id": "org1", "vendor_id": "ghost", "run_id": "run1",
        "evaluation_setup_dict": _empty_setup_dict(),
        "extraction_output_objects": {},  # ghost failed upstream
    }
    res = await nodes.evaluation_per_vendor(state)
    assert res["failed_vendors"][0]["vendor_id"] == "ghost"
    assert "no extraction output" in res["failed_vendors"][0]["error"]


# ── W6 — summary rollup ──────────────────────────────────────────────────────

def test_summarise_critic_metrics_rolls_up_by_agent():
    from tools.smoke_test_graph import _summarise_critic_metrics
    accum = {
        "acme": {
            "extraction": {"blocks": 1, "retries": 1, "retry_success": True, "exhausted": False},
            "evaluation": {"blocks": 0, "retries": 0, "retry_success": False, "exhausted": False},
        },
        "apex": {
            "extraction": {"blocks": 3, "retries": 2, "retry_success": False, "exhausted": True},
        },
    }
    out = _summarise_critic_metrics(accum)
    ext = out["by_agent"]["extraction"]
    assert ext["vendors"] == 2
    assert ext["blocks"] == 4
    assert ext["retry_success"] == 1
    assert ext["exhausted"] == 1
    assert out["by_agent"]["evaluation"]["vendors"] == 1
    assert out["by_vendor"] == accum


def test_summarise_critic_metrics_empty():
    from tools.smoke_test_graph import _summarise_critic_metrics
    assert _summarise_critic_metrics({}) == {"by_agent": {}, "by_vendor": {}}


# ── W7 — external astream-reconstruction must accumulate, not overwrite ──────

def test_astream_reconstruction_accumulates_across_stages():
    """pipeline.py + smoke_test rebuild final_state from astream 'updates' diffs
    via shallow {**state, **diff}. Those diffs are RAW node returns (reducer NOT
    applied), so critic telemetry must be merged explicitly or a later stage's
    emission clobbers the earlier one. This locks in that accumulation loop."""
    # Simulated astream 'updates' diffs: extraction stage (2 vendors), then
    # evaluation stage (2 vendors) — same vendor_ids reused across stages.
    diffs = [
        {"critic_metrics_accum": {"acme": {"extraction": {"blocks": 1}}}},
        {"critic_metrics_accum": {"apex": {"extraction": {"blocks": 0}}}},
        {"critic_metrics_accum": {"acme": {"evaluation": {"blocks": 0}}}},
        {"critic_metrics_accum": {"apex": {"evaluation": {"blocks": 2}}}},
    ]
    final_state: dict = {}
    for diff in diffs:
        prev = final_state.get("critic_metrics_accum") or {}
        final_state = {**final_state, **diff}
        if "critic_metrics_accum" in diff:
            final_state["critic_metrics_accum"] = _merge_critic_metrics(
                prev, diff["critic_metrics_accum"])

    acc = final_state["critic_metrics_accum"]
    # Both stages survive for BOTH vendors — no clobber.
    assert set(acc["acme"]) == {"extraction", "evaluation"}
    assert set(acc["apex"]) == {"extraction", "evaluation"}
    assert acc["acme"]["extraction"]["blocks"] == 1
    assert acc["apex"]["evaluation"]["blocks"] == 2

    # Sanity: a naive shallow merge (the bug) keeps only the LAST diff's value —
    # every prior vendor/stage is dropped entirely.
    naive: dict = {}
    for diff in diffs:
        naive = {**naive, **diff}
    assert naive["critic_metrics_accum"] == {"apex": {"evaluation": {"blocks": 2}}}
