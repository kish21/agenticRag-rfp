"""
E3.e — Regression gates (pure).

`check_gates(aggregate, gates)` compares a benchmark aggregate (the dict produced
by benchmark.metrics.aggregate.build_results) against the thresholds declared in
benchmark/gates.yaml, and returns a GateReport. No IO, no LLM, no DB — so it is
unit-tested in CI (tests/test_benchmark_gates.py). Loading the YAML and printing
the table live in the runner; the decision logic lives here and stays pure.

Fail-closed: a missing/None measured value is a violation — the gate never passes
on absent data (a metric that silently dropped to None must not slip the gate).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

GATES_FILE = Path(__file__).resolve().parents[1] / "gates.yaml"

_DIRECTIONS = ("min", "max")


@dataclass(frozen=True)
class GateRow:
    """One evaluated gate — pass / fail / skip, with the numbers that decided it."""
    metric: str
    direction: str
    threshold: float
    tolerance: float
    measured: Optional[float]
    passed: bool
    reason: str
    skipped: bool = False     # metric not applicable this run (present but None) — not a violation


@dataclass
class GateReport:
    passed: bool
    rows: list[GateRow] = field(default_factory=list)

    @property
    def violations(self) -> list[GateRow]:
        return [r for r in self.rows if not r.passed and not r.skipped]

    @property
    def skipped(self) -> list[GateRow]:
        return [r for r in self.rows if r.skipped]


def load_gates(path: Path = GATES_FILE) -> dict:
    """Read the gate thresholds from YAML. Kept out of check_gates so the decision
    logic stays pure/testable without touching the filesystem."""
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    gates = data.get("gates")
    if not isinstance(gates, dict) or not gates:
        raise ValueError(f"{path} has no non-empty 'gates' mapping")
    return gates


def _evaluate(direction: str, threshold: float, tolerance: float,
              measured: Optional[float]) -> tuple[bool, str]:
    if direction not in _DIRECTIONS:
        # A malformed gate must fail loud, not silently pass.
        return False, f"invalid direction {direction!r} (expected min|max)"
    if measured is None:
        return False, "no measured value (fail-closed)"
    if direction == "min":
        bound = threshold - tolerance
        ok = measured >= bound
        return ok, ("" if ok else
                    f"{measured:g} < floor {bound:g} (threshold {threshold:g} − tol {tolerance:g})")
    bound = threshold + tolerance
    ok = measured <= bound
    return ok, ("" if ok else
                f"{measured:g} > ceiling {bound:g} (threshold {threshold:g} + tol {tolerance:g})")


def check_gates(aggregate: dict, gates: dict) -> GateReport:
    """Evaluate every gate against the aggregate. Pure.

    Three outcomes per gate:
      * PASS / FAIL — the metric was measured and met / missed its threshold.
      * SKIP — the metric is present but None: a ratio/mean whose denominator was
        zero this run (e.g. insufficient_rate on a scenario subset that expects no
        insufficient evidence). Not a regression, so it does not fail the gate.
      * FAIL (fail-closed) — the metric key is ABSENT from the aggregate: a
        typo/rename/disappeared metric must trip the gate, never silently skip.
    """
    rows: list[GateRow] = []
    for metric, spec in gates.items():
        direction = str(spec.get("direction", "")).lower()
        threshold = float(spec.get("threshold", 0))
        tolerance = float(spec.get("tolerance", 0))

        present = metric in aggregate
        raw = aggregate.get(metric)
        # bool is an int subclass but no gated metric is a bare bool — guard anyway.
        numeric = isinstance(raw, (int, float)) and not isinstance(raw, bool)

        if present and raw is None:                 # measured, not applicable → SKIP
            rows.append(GateRow(metric=metric, direction=direction, threshold=threshold,
                                tolerance=tolerance, measured=None, passed=True,
                                reason="not applicable this run (no denominator)", skipped=True))
            continue
        if not present:                              # absent key → fail-closed
            rows.append(GateRow(metric=metric, direction=direction, threshold=threshold,
                                tolerance=tolerance, measured=None, passed=False,
                                reason="metric absent from aggregate (fail-closed)"))
            continue

        measured = float(raw) if numeric else None
        passed, reason = _evaluate(direction, threshold, tolerance, measured)
        rows.append(GateRow(metric=metric, direction=direction, threshold=threshold,
                            tolerance=tolerance, measured=measured, passed=passed, reason=reason))
    return GateReport(passed=not any(not r.passed and not r.skipped for r in rows), rows=rows)


def render_gate_table(report: GateReport) -> str:
    """Human-readable PASS/FAIL table for the runner stdout."""
    lines = ["", "## Regression gates", "",
             "| Gate | Dir | Threshold | Tol | Measured | Result |",
             "|---|---|---|---|---|---|"]
    for r in report.rows:
        meas = "—" if r.measured is None else f"{r.measured:g}"
        if r.skipped:
            verdict = f"SKIP — {r.reason}"
        elif r.passed:
            verdict = "PASS"
        else:
            verdict = f"**FAIL** — {r.reason}"
        lines.append(f"| {r.metric} | {r.direction} | {r.threshold:g} | {r.tolerance:g} "
                     f"| {meas} | {verdict} |")
    lines.append("")
    skipped = f", {len(report.skipped)} skipped" if report.skipped else ""
    lines.append(f"**Gate result: {'PASS' if report.passed else 'FAIL'}** "
                 f"({len(report.violations)} violation(s){skipped})")
    return "\n".join(lines)
