"""
Roll-up: turn (golden, actual) pairs into the committed results artifact.

`evaluate_scenario` runs every pure metric for one scenario; `build_results`
aggregates across scenarios into a `BenchmarkResult` (the JSON artifact) and
`render_markdown` produces the human-readable `metrics.md`. The artifact records
the git commit + config so any number is traceable (exit criterion C2).
"""
from __future__ import annotations

from statistics import mean
from typing import Optional

from pydantic import BaseModel, Field

from benchmark.golden_schema import ScenarioGolden
from benchmark.metrics.actuals import ActualScenario, ActualVendor
from benchmark.metrics.extraction import extraction_quality
from benchmark.metrics.grounding import grounding_accuracy
from benchmark.metrics.retrieval import retrieval_recall
from benchmark.metrics.runtime_cost import runtime_cost
from benchmark.metrics.scoring import score_consistency, scoring_quality


class VendorResult(BaseModel):
    vendor_id: str
    retrieval: dict
    extraction: dict
    grounding: dict
    scoring: dict
    consistency: dict


class ScenarioResult(BaseModel):
    scenario_id: str
    title: str
    stresses: list[str] = Field(default_factory=list)
    vendors: list[VendorResult] = Field(default_factory=list)
    runtime: dict = Field(default_factory=dict)


class BenchmarkResult(BaseModel):
    commit: str
    generated_at: str
    config: dict
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    aggregate: dict = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)


def evaluate_scenario(golden: ScenarioGolden, actual: ActualScenario) -> ScenarioResult:
    by_vendor = {v.vendor_id: v for v in actual.vendors}
    vendor_results: list[VendorResult] = []
    for ev in golden.vendors:
        av = by_vendor.get(ev.vendor_id, ActualVendor(vendor_id=ev.vendor_id))
        vendor_results.append(VendorResult(
            vendor_id=ev.vendor_id,
            retrieval=retrieval_recall(ev, av),
            extraction=extraction_quality(ev, av),
            grounding=grounding_accuracy(av),
            scoring=scoring_quality(ev, av),
            consistency=score_consistency(av),
        ))
    return ScenarioResult(
        scenario_id=golden.scenario_id, title=golden.title, stresses=golden.stresses,
        vendors=vendor_results, runtime=runtime_cost(actual),
    )


def _mean(vals: list[Optional[float]]) -> Optional[float]:
    nums = [v for v in vals if v is not None]
    return round(mean(nums), 4) if nums else None


def build_results(commit: str, generated_at: str, config: dict,
                  scenarios: list[ScenarioResult], failures: list[str]) -> BenchmarkResult:
    vrs = [v for s in scenarios for v in s.vendors]
    agg = {
        "scenarios": len(scenarios),
        "vendors": len(vrs),
        "retrieval_recall": _mean([v.retrieval.get("recall") for v in vrs]),
        "extraction_recall": _mean([v.extraction.get("recall") for v in vrs]),
        "extraction_precision_present": _mean([v.extraction.get("precision_present") for v in vrs]),
        "grounding_accuracy": _mean([v.grounding.get("grounding_accuracy") for v in vrs]),
        "fabricated_citations_total": sum(v.grounding.get("fabricated_citations", 0) for v in vrs),
        "hallucinated_against_absent_total": sum(
            v.extraction.get("hallucinated_against_absent", 0) for v in vrs),
        "band_agreement": _mean([v.scoring.get("band_agreement") for v in vrs]),
        "insufficient_rate": _ratio(
            sum(v.scoring.get("insufficient_correct", 0) for v in vrs),
            sum(v.scoring.get("insufficient_expected", 0) for v in vrs)),
        "forced_when_insufficient_total": sum(
            v.scoring.get("forced_when_insufficient", 0) for v in vrs),
        "mandatory_accuracy": _mean([v.scoring.get("mandatory_accuracy") for v in vrs]),
        "rejection_correct": _ratio(
            sum(1 for v in vrs if v.scoring.get("rejection_correct") is True),
            sum(1 for v in vrs if v.scoring.get("rejection_correct") is not None)),
        "total_cost_usd": round(sum(s.runtime.get("total_cost_usd", 0.0) for s in scenarios), 6),
        "total_wall_clock_s": round(sum(s.runtime.get("wall_clock_s", 0.0) for s in scenarios), 3),
        "operational_failures": sum(
            1 for s in scenarios if s.runtime.get("errored") or s.runtime.get("blocked")),
    }
    return BenchmarkResult(commit=commit, generated_at=generated_at, config=config,
                           scenarios=scenarios, aggregate=agg, failures=failures)


def _ratio(numer: int, denom: int) -> Optional[float]:
    return round(numer / denom, 4) if denom else None


def _fmt(v) -> str:
    return "—" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def render_markdown(result: BenchmarkResult) -> str:
    a = result.aggregate
    L = [
        "# E3 Evidence-Quality Benchmark — Results",
        "",
        f"- **Commit:** `{result.commit}`",
        f"- **Generated:** {result.generated_at}",
        f"- **Config:** {result.config}",
        "",
        "> Baseline run (no pass/fail gate — see docs/dev/E3_EXIT_CRITERIA.md). "
        "Every number below is computed by the runner from real pipeline outputs.",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Retrieval recall | {_fmt(a.get('retrieval_recall'))} |",
        f"| Extraction recall | {_fmt(a.get('extraction_recall'))} |",
        f"| Extraction precision (present) | {_fmt(a.get('extraction_precision_present'))} |",
        f"| **Grounding/citation accuracy** | {_fmt(a.get('grounding_accuracy'))} |",
        f"| **Fabricated citations (total)** | {_fmt(a.get('fabricated_citations_total'))} |",
        f"| Hallucinated vs absent (total) | {_fmt(a.get('hallucinated_against_absent_total'))} |",
        f"| Scoring band agreement | {_fmt(a.get('band_agreement'))} |",
        f"| Insufficient-evidence rate | {_fmt(a.get('insufficient_rate'))} |",
        f"| Forced-when-insufficient (total) | {_fmt(a.get('forced_when_insufficient_total'))} |",
        f"| Mandatory accuracy | {_fmt(a.get('mandatory_accuracy'))} |",
        f"| Rejection correct | {_fmt(a.get('rejection_correct'))} |",
        f"| Total cost (USD) | {_fmt(a.get('total_cost_usd'))} |",
        f"| Total wall-clock (s) | {_fmt(a.get('total_wall_clock_s'))} |",
        f"| Operational failures | {_fmt(a.get('operational_failures'))} |",
        "",
        "## Per scenario",
        "",
        "| Scenario | Retr. | Extr.R | Extr.P | Grounding | Fabricated | Mand. | Insuf. | Cost $ | Wall s |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in result.scenarios:
        for v in s.vendors:
            L.append(
                f"| {s.scenario_id}/{v.vendor_id} "
                f"| {_fmt(v.retrieval.get('recall'))} "
                f"| {_fmt(v.extraction.get('recall'))} "
                f"| {_fmt(v.extraction.get('precision_present'))} "
                f"| {_fmt(v.grounding.get('grounding_accuracy'))} "
                f"| {_fmt(v.grounding.get('fabricated_citations'))} "
                f"| {_fmt(v.scoring.get('mandatory_accuracy'))} "
                f"| {_fmt(v.scoring.get('insufficient_rate'))} "
                f"| {_fmt(s.runtime.get('total_cost_usd'))} "
                f"| {_fmt(s.runtime.get('wall_clock_s'))} |"
            )
    if result.failures:
        L += ["", "## Failures", ""] + [f"- {f}" for f in result.failures]
    return "\n".join(L) + "\n"
