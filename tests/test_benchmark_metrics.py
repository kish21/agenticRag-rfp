"""
Unit tests for the pure E3 metric functions (exit criterion C4).

Fully synthetic in/out — no DB, no LLM, no pipeline. Verifies the *math* of every
metric so a real benchmark run can be trusted to compute what we think it does.
"""
from __future__ import annotations

from benchmark.golden_schema import (
    ExpectedCriterion, ExpectedFact, ExpectedMandatory, ExpectedVendor,
)
from benchmark.metrics.actuals import (
    ActualComplianceDecision, ActualCriterionScore, ActualFact, ActualScenario, ActualVendor,
)
from benchmark.metrics import matching
from benchmark.metrics.extraction import extraction_quality
from benchmark.metrics.grounding import grounding_accuracy
from benchmark.metrics.retrieval import retrieval_recall
from benchmark.metrics.scoring import score_consistency, scoring_quality
from benchmark.metrics.runtime_cost import runtime_cost
from benchmark.metrics.aggregate import build_results, evaluate_scenario, render_markdown
from benchmark.golden_schema import ScenarioGolden


# ── matching ──────────────────────────────────────────────────────────────────

def test_values_match_numbers_and_strings():
    assert matching.values_match(10000000, 10000000.0)
    assert matching.values_match("£10,000,000", 10000000)
    assert matching.values_match("ISO 27001", "ISO 27001:2022")   # containment
    assert not matching.values_match(10000000, 2000000)
    assert not matching.values_match("ISO 27001", "SOC 2")


def test_values_match_is_punctuation_insensitive_but_not_synonym():
    # Cosmetic format variants must match (E3.a fix)...
    assert matching.values_match("financial services", "financial-services")
    assert matching.values_match("ISO 27001:2022", "ISO 27001 2022")
    # ...but genuinely different words must NOT (don't fold valid/expired together).
    assert not matching.values_match("valid", "expired")
    assert not matching.values_match("current", "lapsed")


def test_key_fields_match_requires_all():
    assert matching.key_fields_match({"a": 1, "b": "x"}, {"a": 1, "b": "x y"})
    assert not matching.key_fields_match({"a": 1, "b": "x"}, {"a": 1})        # missing b
    assert not matching.key_fields_match({"a": 1}, {"a": 2})                  # wrong value


# ── retrieval ───────────────────────────────────────────────────────────────--

def test_retrieval_recall_counts_only_present():
    exp = ExpectedVendor(vendor_id="v", vendor_pdf="v.pdf", facts=[
        ExpectedFact(fact_type="sla", grounding_substring="15-minute response", present=True),
        ExpectedFact(fact_type="pricing", grounding_substring="£1,200,000", present=True),
        ExpectedFact(fact_type="insurance", present=False),
    ])
    act = ActualVendor(vendor_id="v", retrieved_texts=["… a 15-minute response time …"])
    r = retrieval_recall(exp, act)
    assert r["present_facts"] == 2 and r["retrieved"] == 1 and r["recall"] == 0.5


# ── extraction ──────────────────────────────────────────────────────────────--

def test_extraction_recall_precision_and_hallucination():
    exp = ExpectedVendor(vendor_id="v", vendor_pdf="v.pdf", facts=[
        ExpectedFact(fact_type="certification", key_fields={"standard_name": "ISO 27001"},
                     grounding_substring="ISO 27001", present=True),
        ExpectedFact(fact_type="insurance", present=False),   # doc omits insurance
    ])
    act = ActualVendor(vendor_id="v", facts=[
        ActualFact(fact_type="certification", fields={"standard_name": "ISO 27001:2022"},
                   grounding_quote="ISO 27001:2022"),
        ActualFact(fact_type="insurance", fields={"amount": 5000000},
                   grounding_quote="invented"),               # hallucinated vs absent
    ])
    q = extraction_quality(exp, act)
    assert q["per_type"]["certification"]["recall"] == 1.0
    assert q["per_type"]["insurance"]["hallucinated_against_absent"] == 1
    assert q["hallucinated_against_absent"] == 1


# ── grounding ───────────────────────────────────────────────────────────────--

def test_grounding_flags_fabricated_quote():
    act = ActualVendor(
        vendor_id="v",
        source_text="Acme holds ISO 27001:2022 certification, valid until 2027.",
        facts=[
            ActualFact(fact_type="certification", grounding_quote="ISO 27001:2022 certification"),
            ActualFact(fact_type="insurance", grounding_quote="£50,000,000 cover"),  # not in source
        ],
    )
    g = grounding_accuracy(act)
    assert g["honest_citations"] == 1 and g["fabricated_citations"] == 1
    assert g["grounding_accuracy"] == 0.5
    assert g["fabricated"][0]["fact_type"] == "insurance"


# ── scoring ─────────────────────────────────────────────────────────────────--

def test_scoring_band_insufficient_and_mandatory():
    exp = ExpectedVendor(
        vendor_id="v", vendor_pdf="v.pdf",
        mandatory=[ExpectedMandatory(check_id="c1", outcome="pass"),
                   ExpectedMandatory(check_id="c2", outcome="insufficient_evidence")],
        criteria=[ExpectedCriterion(criterion_id="k1", expectation="9-10"),
                  ExpectedCriterion(criterion_id="k2", expectation="insufficient")],
        expected_rejected=False,
    )
    act = ActualVendor(
        vendor_id="v",
        criterion_scores=[ActualCriterionScore(criterion_id="k1", raw_score=10),
                          ActualCriterionScore(criterion_id="k2", raw_score=0)],  # forced, not insufficient
        compliance_decisions=[ActualComplianceDecision(check_id="c1", decision="pass"),
                              ActualComplianceDecision(check_id="c2", decision="insufficient_evidence")],
        rejected=False,
    )
    s = scoring_quality(exp, act)
    assert s["band_agreement"] == 1.0                 # k1 in 9-10
    assert s["insufficient_correct"] == 0             # k2 was forced to a 0
    assert s["forced_when_insufficient"] == 1
    assert s["mandatory_accuracy"] == 1.0
    assert s["rejection_correct"] is True


def test_scoring_credits_insufficient_when_flagged():
    exp = ExpectedVendor(vendor_id="v", vendor_pdf="v.pdf",
                         criteria=[ExpectedCriterion(criterion_id="k", expectation="insufficient")])
    act = ActualVendor(vendor_id="v",
                       criterion_scores=[ActualCriterionScore(criterion_id="k", insufficient=True)])
    s = scoring_quality(exp, act)
    assert s["insufficient_rate"] == 1.0 and s["forced_when_insufficient"] == 0


def test_score_consistency_variance():
    act = ActualVendor(vendor_id="v",
                       repeat_scores={"k1": [8, 8, 8], "k2": [6, 8, 7]})
    c = score_consistency(act)
    assert c["criteria_with_repeats"] == 2 and c["mean_score_stdev"] > 0


# ── runtime/cost + aggregate ──────────────────────────────────────────────────

def test_runtime_cost_passthrough():
    sc = ActualScenario(scenario_id="s", node_timings_s={"ingestion": 7.0, "planner": 0.1},
                        cost={"total_cost_usd": 0.42, "total_calls": 9})
    rc = runtime_cost(sc)
    assert rc["wall_clock_s"] == 7.1 and rc["slowest_stage"] == "ingestion"
    assert rc["total_cost_usd"] == 0.42 and rc["errored"] is False


def test_aggregate_and_markdown_roundtrip():
    golden = ScenarioGolden(
        scenario_id="01_clean", title="Clean", stresses=["baseline"],
        rfp_pdf="rfp.pdf", setup_json="setup.json",
        vendors=[ExpectedVendor(vendor_id="acme", vendor_pdf="v.pdf",
                                facts=[ExpectedFact(fact_type="pricing",
                                                    grounding_substring="£1,200,000", present=True)])],
    )
    actual = ActualScenario(
        scenario_id="01_clean", node_timings_s={"x": 1.0}, cost={"total_cost_usd": 0.1},
        vendors=[ActualVendor(vendor_id="acme", source_text="fee is £1,200,000",
                              retrieved_texts=["fee is £1,200,000"],
                              facts=[ActualFact(fact_type="pricing", fields={},
                                                grounding_quote="£1,200,000")])],
    )
    sr = evaluate_scenario(golden, actual)
    res = build_results("abc123", "2026-05-31T00:00:00Z", {"model": "test"}, [sr], [])
    assert res.aggregate["grounding_accuracy"] == 1.0
    assert res.aggregate["fabricated_citations_total"] == 0
    md = render_markdown(res)
    assert "Grounding/citation accuracy" in md and "01_clean/acme" in md


# ── pure adapter mapping (final_state → ActualScenario) ───────────────────────

def test_state_to_actual_maps_pipeline_state():
    from benchmark.runner.pipeline_adapter import state_to_actual

    golden = ScenarioGolden(
        scenario_id="06_missing_evidence", title="Missing", stresses=["missing"],
        rfp_pdf="rfp.pdf", setup_json="setup.json",
        vendors=[ExpectedVendor(vendor_id="omega", vendor_pdf="v.pdf")],
    )
    # final_state with dict-shaped objects (state_to_actual handles dict or model).
    final_state = {
        "extraction_output_objects": {"omega": {
            "certifications": [],
            "slas": [{"priority_level": "P1", "response_minutes": 15,
                      "grounding_quote": "15-minute response", "source_chunk_id": "c1",
                      "confidence": 0.9}],
            "insurance": [], "projects": [], "pricing": [], "extracted_facts": [],
        }},
        "evaluation_output_objects": {"omega": {
            "criterion_scores": [{"criterion_id": "crit-security", "raw_score": 0, "confidence": 0.4}],
            "compliance_decisions": [{"check_id": "chk-iso27001",
                                      "decision": "insufficient_evidence", "confidence": 0.2}],
        }},
        "retrieval_output_objects": {"omega": {"chunks": [{"text": "a 15-minute response time"}]}},
        "decision_output": {"rejected_vendors": [{"vendor_id": "omega"}], "shortlisted_vendors": []},
        "blocked": False, "blocked_agent": "", "error_message": "",
    }
    actual = state_to_actual(golden, final_state, {"omega": "doc text"}, {"ingestion": 5.0},
                             {"total_cost_usd": 0.3})
    v = actual.vendors[0]
    assert v.vendor_id == "omega" and v.rejected is True
    assert v.facts[0].fact_type == "sla" and v.facts[0].source_chunk_id == "c1"
    assert v.retrieved_texts == ["a 15-minute response time"]
    assert v.compliance_decisions[0].decision == "insufficient_evidence"
    assert actual.node_timings_s == {"ingestion": 5.0} and actual.cost["total_cost_usd"] == 0.3
