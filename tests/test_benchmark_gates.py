"""
Unit tests for the E3.e regression gate logic (pure — no IO/LLM/DB).

Verifies the decision math of benchmark.metrics.gates.check_gates: direction
handling, tolerance, zero-tolerance invariants, fail-closed on missing values, and
that the real benchmark/gates.yaml is loadable and well-formed.
"""
from __future__ import annotations

import pytest

from benchmark.metrics.gates import (
    GATES_FILE, check_gates, load_gates, render_gate_table,
)


# ── direction + tolerance math ──────────────────────────────────────────────

def test_min_gate_passes_at_and_above_floor():
    gates = {"grounding_accuracy": {"direction": "min", "threshold": 1.0, "tolerance": 0.05}}
    assert check_gates({"grounding_accuracy": 1.0}, gates).passed
    assert check_gates({"grounding_accuracy": 0.96}, gates).passed   # within tolerance
    assert check_gates({"grounding_accuracy": 0.95}, gates).passed   # exactly at floor


def test_min_gate_fails_below_floor():
    gates = {"grounding_accuracy": {"direction": "min", "threshold": 1.0, "tolerance": 0.05}}
    report = check_gates({"grounding_accuracy": 0.94}, gates)
    assert not report.passed
    assert [v.metric for v in report.violations] == ["grounding_accuracy"]
    assert "floor" in report.violations[0].reason


def test_max_gate_passes_at_and_below_ceiling_fails_above():
    gates = {"forced_when_insufficient_total": {"direction": "max", "threshold": 0, "tolerance": 1}}
    assert check_gates({"forced_when_insufficient_total": 1}, gates).passed   # at ceiling
    report = check_gates({"forced_when_insufficient_total": 2}, gates)        # above
    assert not report.passed
    assert "ceiling" in report.violations[0].reason


# ── zero-tolerance integrity invariants ─────────────────────────────────────

def test_zero_tolerance_invariant_trips_on_any_increase():
    gates = {"fabricated_citations_total": {"direction": "max", "threshold": 0, "tolerance": 0}}
    assert check_gates({"fabricated_citations_total": 0}, gates).passed
    assert not check_gates({"fabricated_citations_total": 1}, gates).passed


# ── fail-closed on missing / malformed ──────────────────────────────────────

def test_absent_metric_key_is_a_violation_fail_closed():
    """A metric KEY missing from the aggregate (typo/rename/disappeared) must trip
    the gate, never silently pass — distinct from a present-but-None N/A value."""
    gates = {"grounding_accuracy": {"direction": "min", "threshold": 1.0, "tolerance": 0.05}}
    report = check_gates({}, gates)                          # key absent entirely
    assert not report.passed
    assert "fail-closed" in report.violations[0].reason


def test_present_none_value_is_skipped_not_failed():
    """A ratio/mean that is None because its denominator was zero this run (e.g.
    insufficient_rate on a subset with no insufficient-expected scenarios) is N/A,
    not a regression — it must SKIP and not fail the gate."""
    gates = {"insufficient_rate": {"direction": "min", "threshold": 1.0, "tolerance": 0.2}}
    report = check_gates({"insufficient_rate": None}, gates)
    assert report.passed                                    # skip does not fail the gate
    assert report.violations == []
    assert [r.metric for r in report.skipped] == ["insufficient_rate"]


def test_skip_does_not_mask_a_real_violation_on_another_gate():
    gates = {
        "insufficient_rate": {"direction": "min", "threshold": 1.0, "tolerance": 0.2},
        "fabricated_citations_total": {"direction": "max", "threshold": 0, "tolerance": 0},
    }
    report = check_gates({"insufficient_rate": None, "fabricated_citations_total": 2}, gates)
    assert not report.passed
    assert {v.metric for v in report.violations} == {"fabricated_citations_total"}
    assert {r.metric for r in report.skipped} == {"insufficient_rate"}


def test_invalid_direction_fails_loud():
    gates = {"x": {"direction": "between", "threshold": 1.0, "tolerance": 0.0}}
    report = check_gates({"x": 1.0}, gates)
    assert not report.passed
    assert "invalid direction" in report.violations[0].reason


# ── multi-gate aggregation ──────────────────────────────────────────────────

def test_report_aggregates_multiple_violations():
    gates = {
        "grounding_accuracy": {"direction": "min", "threshold": 1.0, "tolerance": 0.0},
        "fabricated_citations_total": {"direction": "max", "threshold": 0, "tolerance": 0},
        "mandatory_accuracy": {"direction": "min", "threshold": 1.0, "tolerance": 0.0},
    }
    agg = {"grounding_accuracy": 0.9, "fabricated_citations_total": 2, "mandatory_accuracy": 1.0}
    report = check_gates(agg, gates)
    assert not report.passed
    assert {v.metric for v in report.violations} == {"grounding_accuracy", "fabricated_citations_total"}
    assert len(report.rows) == 3            # all evaluated, even the passing one


def test_render_table_marks_pass_and_fail():
    gates = {"fabricated_citations_total": {"direction": "max", "threshold": 0, "tolerance": 0}}
    table = render_gate_table(check_gates({"fabricated_citations_total": 3}, gates))
    assert "FAIL" in table and "fabricated_citations_total" in table


# ── the real committed gates.yaml ───────────────────────────────────────────

def test_real_gates_yaml_loads_and_is_well_formed():
    gates = load_gates(GATES_FILE)
    assert gates, "gates.yaml must declare at least one gate"
    for metric, spec in gates.items():
        assert spec["direction"] in ("min", "max"), f"{metric} has bad direction"
        assert isinstance(spec["threshold"], (int, float))
        assert isinstance(spec.get("tolerance", 0), (int, float))


def test_every_gate_metric_exists_in_the_real_aggregate():
    """Guard the implicit gates.yaml ↔ aggregate contract: every gated metric must
    be a key the runner actually emits (build_results aggregate). A typo or a
    renamed aggregate key would otherwise fail-closed forever, masquerading as a
    real regression. Builds an empty-but-well-formed aggregate to read its keys."""
    from benchmark.metrics.aggregate import build_results

    agg_keys = set(build_results(
        commit="x", generated_at="x", config={}, scenarios=[], failures=[],
    ).aggregate.keys())
    gate_keys = set(load_gates(GATES_FILE).keys())
    missing = gate_keys - agg_keys
    assert not missing, f"gates.yaml references metrics absent from the aggregate: {missing}"


def test_committed_baseline_passes_its_own_gates():
    """The committed thresholds must pass against the reranked baseline they were
    set from — a gate file that fails its own baseline is mis-set. Numbers from the
    committed reranked run results_20260602T204245Z (RERANKER_PROVIDER=modal)."""
    gates = load_gates(GATES_FILE)
    baseline = {
        "grounding_accuracy": 1.0, "fabricated_citations_total": 0,
        "hallucinated_against_absent_total": 0, "operational_failures": 0,
        "blocked_vendors": 0, "rejection_correct": 1.0, "mandatory_accuracy": 1.0,
        "insufficient_rate": 1.0, "forced_when_insufficient_total": 0,
        "retrieval_recall": 1.0, "extraction_recall": 0.8778,
    }
    report = check_gates(baseline, gates)
    assert report.passed, f"baseline trips its own gates: {[v.reason for v in report.violations]}"
