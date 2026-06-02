"""
E3 benchmark CLI — the single command from exit-criterion C1.

    python -m benchmark.runner.run_benchmark [--scenario 01_clean] [--repeats 3]

Runs each scenario through the real pipeline, compares to its golden file, and
writes a timestamped, traceable artifact pair to benchmark/results/:
    results_<UTC>.json   (full BenchmarkResult — every number + raw per-scenario)
    results_<UTC>.md     (human-readable summary)

Fails loud (C3): a scenario that errors is recorded in `failures[]` and the
process exits non-zero — it is never silently skipped. This is a baseline run
(C/ E3 decision): it reports numbers and only fails on operational errors.
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

from app.config import settings
from benchmark.golden_schema import ScenarioGolden
from benchmark.metrics.aggregate import build_results, evaluate_scenario, render_markdown
from benchmark.runner.pipeline_adapter import run_scenario

SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"
RESULTS = Path(__file__).resolve().parents[1] / "results"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       text=True).strip()
    except Exception:
        return "unknown"


def _config() -> dict:
    return {
        "llm_provider": settings.llm_provider,
        "model": settings.platform.llm.primary_model,
        "embedding_provider": settings.embedding_provider,
        "reranker_provider": settings.reranker_provider,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the E3 evidence-quality benchmark.")
    ap.add_argument("--scenario", help="run only this scenario id (default: all)")
    ap.add_argument("--repeats", type=int, default=1,
                    help="re-runs per scenario for scoring-consistency (default 1)")
    ap.add_argument("--gate", action="store_true",
                    help="E3.e: after the run, check the aggregate against benchmark/gates.yaml "
                         "and exit non-zero on any regression (default: report-only, no gate)")
    args = ap.parse_args(argv)

    dirs = sorted(d for d in SCENARIOS.iterdir() if d.is_dir())
    if args.scenario:
        dirs = [d for d in dirs if d.name == args.scenario]
        if not dirs:
            print(f"[ABORT] no scenario {args.scenario!r}")
            return 2

    scenario_results = []
    failures: list[str] = []
    for d in dirs:
        golden = ScenarioGolden.model_validate_json((d / "golden.json").read_text(encoding="utf-8"))
        print(f"→ running {golden.scenario_id} …", flush=True)
        try:
            actual = run_scenario(d, golden, repeats=args.repeats)
            scenario_results.append(evaluate_scenario(golden, actual))
            if actual.error or actual.blocked:
                failures.append(f"{golden.scenario_id}: "
                                f"{'blocked@' + actual.blocked_agent if actual.blocked else actual.error}")
        except Exception as exc:                      # fail loud (C3)
            failures.append(f"{golden.scenario_id}: EXCEPTION {type(exc).__name__}: {exc}")
            print(f"  [FAIL] {golden.scenario_id}: {exc}", flush=True)

    result = build_results(
        commit=_git_commit(),
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        config=_config(), scenarios=scenario_results, failures=failures,
    )

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (RESULTS / f"results_{stamp}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    (RESULTS / f"results_{stamp}.md").write_text(render_markdown(result), encoding="utf-8")
    print(f"\nWrote benchmark/results/results_{stamp}.json (+ .md)")
    print(f"  grounding_accuracy={result.aggregate.get('grounding_accuracy')}  "
          f"fabricated={result.aggregate.get('fabricated_citations_total')}  "
          f"cost=${result.aggregate.get('total_cost_usd')}  failures={len(failures)}")
    if result.blocked_vendors:                         # E3.b.2 — surface loudly (C3)
        print(f"  [BLOCKED] {len(result.blocked_vendors)} vendor(s) dropped pre-assessment "
              "(excluded from quality rates):")
        for b in result.blocked_vendors:
            print(f"    - {b['scenario']}/{b['vendor_id']} @ {b['stage']}")

    gate_failed = False
    if args.gate:                                      # E3.e — opt-in regression gate
        from benchmark.metrics.gates import check_gates, load_gates, render_gate_table
        report = check_gates(result.aggregate, load_gates())
        print(render_gate_table(report))
        gate_failed = not report.passed

    # Exit non-zero on an operational failure (C3) OR a tripped gate (E3.e).
    return 1 if (failures or gate_failed) else 0


if __name__ == "__main__":
    sys.exit(main())
