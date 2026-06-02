# E3.b.2 — Grader Robustness: a blocked vendor is not a low score

**Status:** built 2026-06-02 (branch `e3.b.2-grader-robustness`).
**Contract:** extends [`E3_EXIT_CRITERIA.md`](E3_EXIT_CRITERIA.md) (criteria G/H/I/J below).

## The integrity hole this closes

The E3 benchmark is the audit-ready proof that the product **never fabricates
evidence or forces a score**. But a vendor whose stage was **critic-blocked,
dropped, or failed upstream** arrives at the metrics with *empty*
`criterion_scores` and `compliance_decisions` — which was **indistinguishable
from "assessed, found insufficient / wrong."**

Before this change, `scoring_quality()` read that empty vendor and silently:
- counted every `insufficient`-expected criterion as `forced_when_insufficient`
  (`benchmark/metrics/scoring.py` — `cs is None` fell to the `else`), and
- counted every mandatory check as wrong (`next(..., None) != outcome`).

So a future HARD-block (e.g. a fabrication guard firing and dropping a vendor)
would be **silently mis-scored as a quality failure**, corrupting the very
numbers the benchmark exists to defend. (The bug that first exposed this —
epsilon scoring 0 in `05_conflicting` — had already cleared on master via
#200/#202, so this is **defensive** work: make the instrument honest before a
real block ever reaches it. It is also a prerequisite for a trustworthy E3.e
regression gate.)

## What changed (read-only on the product; benchmark-side only)

The product pipeline already records blocked vendors in
`final_state["failed_vendors"]` (`{vendor_id, stage, error, ts}`), appended by
`app/pipeline/critic_retry.py` and the upstream-missing guards in
`app/pipeline/nodes.py`. **This change only reads that — no product behaviour
changes.**

| Where | Change |
|---|---|
| `benchmark/metrics/actuals.py` | `ActualVendor` gains `blocked_stage: str\|None` + `blocked_error: str`. `None` ⇒ normally assessed. Never inferred from empty lists. |
| `benchmark/runner/pipeline_adapter.py` | `state_to_actual` reads `failed_vendors`, populates `blocked_stage` (first entry per vendor = originating failure). |
| `benchmark/metrics/scoring.py` | `scoring_quality` short-circuits a `blocked_stage`-set vendor via `_blocked_result` — every quality rate excluded, `blocked: True` surfaced. |
| `benchmark/metrics/aggregate.py` | aggregate gains a `blocked_vendors` count + a `BenchmarkResult.blocked_vendors` detail list; markdown shows a row + a dedicated section. |
| `benchmark/runner/run_benchmark.py` | prints a loud `[BLOCKED]` summary line per blocked vendor. |

## Policy (signed off 2026-06-02): exclude + report separately

A blocked vendor is **pulled out of the quality-rate denominators** (mandatory
accuracy, insufficient rate, forced-when-insufficient) and surfaced **only** as a
loud, separate `blocked_vendors` count. Rationale: a block is an **operational
anomaly to flag**, not an evidence-quality score — it matches the existing C3
"fail loud" guarantee without distorting the grounding/mandatory numbers. The
alternative (keep it in denominators, bucketed) was rejected: an un-assessed
vendor is not a quality data point.

## Exit criteria — status

| ID | Criterion | Status |
|----|-----------|--------|
| G1 | `ActualVendor.blocked_stage`/`blocked_error`; no empty-list inference | ✅ `actuals.py` + test |
| G2 | `state_to_actual` populates from `failed_vendors` | ✅ `test_state_to_actual_marks_blocked_vendor_from_failed_vendors` |
| H1 | blocked vendor excluded from rates; `blocked_vendors` count | ✅ `_blocked_result` + `test_scoring_excludes_blocked_vendor_distinctly` |
| H2 | blocked ≠ assessed-insufficient (only diff = `blocked_stage`) | ✅ same test contrasts both |
| I1 | artifact (JSON + md) surfaces per-vendor blocks | ✅ `test_aggregate_surfaces_blocked_vendors` |
| I2 | no regression on the 6 real scenarios (`blocked_vendors=0`, numbers byte-unchanged) | ⏳ needs a full benchmark run (change is additive — only a new `Blocked vendors \| 0` md row) |
| J1 | metrics stay pure / CI-tested, no API spend | ✅ |
| J2 | no hardcoding (stage from `failed_vendors`, contrast structural) | ✅ |
| J3 | full suite + contracts + drift green; `/code-review` | ✅ 266 green, 14/14, drift OK |
| J4 | doc reconciled + cross-linked | ✅ this doc |

## How to verify

- Unit (no spend): `pytest tests/test_benchmark_metrics.py -q` (15 green).
- Integration (I2, ~$0.36, needs docker postgres+qdrant + HF egress):
  `PYTHONUTF8=1 python -m benchmark.runner.run_benchmark` → the aggregate must
  match `results_20260602T071625Z.md` and show `Blocked vendors | 0`.
