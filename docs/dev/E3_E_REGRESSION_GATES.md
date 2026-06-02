# E3.e — Regression Gates: the benchmark fails loud when quality drops

**Status:** built 2026-06-02 (branch `e3.e-regression-gates`).
**Contract:** extends [`E3_EXIT_CRITERIA.md`](E3_EXIT_CRITERIA.md) "DECISION — baseline first":
the baseline run *records* numbers with no pass/fail gate; **this** turns the
recorded numbers into honest thresholds and a check that fails when a future
change regresses below them. Depends on **E3.b.2** (a blocked vendor is excluded
from the rates, never silently mis-scored — without it a gate could be tripped or
masked by a block) — see [`E3_B2_GRADER_ROBUSTNESS.md`](E3_B2_GRADER_ROBUSTNESS.md).

## Why a prerequisite fix had to land first: the reranker was never running

The gate is only meaningful if it measures the pipeline customers actually run.
It wasn't. The benchmark provisions a throw-away org but **never wrote an
`org_settings` row**, so `get_org_settings()` returned the in-memory defaults, and
every quality preset in `product.yaml` hardcodes `reranker_provider: "bge"` (one
shared `&unified_config` anchor). The retrieval agent passes that per-org value as
`rerank(..., provider="bge")` ([`app/agents/retrieval.py`](../../app/agents/retrieval.py)),
and the explicit `provider=` argument **overrides** the global `RERANKER_PROVIDER`
from `.env`. On a box with no HuggingFace egress, `bge`'s CrossEncoder download
throws → `rerank()`'s handler falls back to **vector-score order** (`_rerank_none`)
with only a `logger.warning`. Net effect: **the benchmark silently measured
un-reranked retrieval** regardless of `.env`. A threshold set on those numbers
would lock in the wrong pipeline.

### Fix (decision 2026-06-02): seed the bench org to honour `.env`

Benchmark-scoped, product precedence untouched. `run_scenario` now writes an
`org_settings` row for its throw-away org with `reranker_provider =
settings.reranker_provider` (i.e. `.env`). Real tenants still resolve their own
per-org setting first — only the benchmark's own org is seeded. We bypass
`upsert_org_settings` deliberately: it force-overlays the tier preset, which would
re-drop `modal` back to the preset's `bge`. The gate run uses
`RERANKER_PROVIDER=modal` → the deployed Modal BGE CrossEncoder
(`deploy/modal_app.py::rerank_on_modal`) — same open-source model, runs server-side,
no local HF egress, dev/prod parity.

(The deeper product smell — `.env RERANKER_PROVIDER` being dead config because the
preset always wins — is logged for a separate product decision; not fixed here to
keep blast radius to the benchmark.)

## What changed

| Where | Change |
|---|---|
| `benchmark/runner/pipeline_adapter.py` | `_seed_org_settings(org_id)` writes an `org_settings` row with `reranker_provider = settings.reranker_provider`; called in `run_scenario` after the org is provisioned. The recorded `config.reranker_provider` now reflects what actually ran. |
| `benchmark/gates.yaml` | **Config, no hardcoding.** The regression thresholds (min grounding, max fabricated, min mandatory/insufficient/rejection, max forced, max op-failures, max blocked) + how each is compared. |
| `benchmark/metrics/gates.py` | **Pure** `check_gates(aggregate, thresholds) -> GateReport`: every threshold → pass/violation with the measured-vs-required values. No IO, CI-tested. |
| `benchmark/runner/run_benchmark.py` | new `--gate` flag: load `gates.yaml`, run `check_gates` on the produced aggregate, print a PASS/FAIL gate table, and exit non-zero on any violation. **Default stays report-only** (baseline contract preserved — `--gate` is opt-in for the scheduled run). |

## Threshold policy (signed off 2026-06-02)

- **Direction + margin, not the raw number.** Each gate is `min`/`max` with a small
  tolerance so normal LLM run-to-run noise does not trip it, but a real regression
  does. Integrity invariants that must never move (`fabricated_citations = 0`,
  `operational_failures = 0`, `blocked_vendors = 0`) are exact, zero-tolerance.
- **Set from a real reranked baseline**, captured with `RERANKER_PROVIDER=modal`
  after the seeding fix — never guessed.
- **Scheduled / on-demand, not per-PR.** Real-LLM runs are too costly/flaky for
  every PR (per `E3_EXIT_CRITERIA.md` out-of-scope). The mechanism is built and
  runnable now (`--gate`); wiring an actual cron schedule is **deferred** (matches
  the project's "Modal cron = recurring $ for zero benefit until a real cadence is
  needed" stance). When a cadence is chosen, a scheduled runner calls
  `run_benchmark --gate` and alerts on a non-zero exit.

## Exit criteria — status

| ID | Criterion | Status |
|----|-----------|--------|
| K1 | Benchmark honours `RERANKER_PROVIDER`; reranker actually runs (not vector fallback) | ✅ seeding + `results_20260602T204245Z` config records `reranker_provider: modal`; retrieval logs show real rerank scores |
| K2 | Thresholds live in `gates.yaml` (config), no hardcoded numbers in code | ✅ `benchmark/gates.yaml` |
| K3 | `check_gates` is pure + CI-tested (pass / single-violation / multi-violation) | ✅ `tests/test_benchmark_gates.py` (11) |
| K4 | `--gate` exits non-zero on violation; default run stays report-only | ✅ `run_benchmark.py` `--gate` glue; gate-check verified against the committed artifact (all PASS) |
| K5 | Zero-tolerance invariants (fabricated / op-failures / blocked) exact | ✅ tol 0 in `gates.yaml` + `test_zero_tolerance_invariant_trips_on_any_increase` |
| K6 | Thresholds set from a real reranked baseline, committed as the artifact | ✅ `results_20260602T204245Z.{json,md}` |
| K7 | full suite + contracts + drift green; `/code-review` | ⏳ |
| K8 | doc reconciled + cross-linked | ✅ this doc |

### Measured reranked baseline (`results_20260602T204245Z`, gpt-4o + Modal BGE)

grounding **1.0** · fabricated **0** · hallucinated-vs-absent **0** · mandatory **1.0** ·
insufficient-rate **1.0** · forced **0** · rejection **1.0** · retrieval-recall **1.0** ·
**extraction-recall 0.88** (was 0.79 un-reranked — reranking measurably helped) ·
op-failures **0** · blocked **0** · cost **$0.37**. The committed `gates.yaml` passes
this baseline with margin (`check_gates` → 0 violations).

## How to verify

- Unit (no spend): `pytest tests/test_benchmark_gates.py -q`.
- Gate (needs docker postgres+qdrant + deployed Modal app, ~$0.3):
  `PYTHONUTF8=1 RERANKER_PROVIDER=modal python -m benchmark.runner.run_benchmark --gate`
  → exits 0 and prints a green gate table; intentionally lowering a `gates.yaml`
  floor below the measured value and re-checking the committed artifact must exit 1.
