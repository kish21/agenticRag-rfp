# E3.d — Coverage-normalised ranking

**Status:** DONE 2026-06-02 · **Owner:** session 2026-06-02 · **Lever:** real product feature (vision-aligned, domain-agnostic)

## Result (measured)

7 deterministic unit tests cover all exit criteria (coverage maths, no-change-at-full-coverage
invariant, the partial-excellent-outranks-full-mediocre flip, the config-driven low-coverage flag).
Full suite **263 green** (256 + 7); contracts 14/14; drift OK. Measure-first benchmark
(`benchmark/results/results_20260602T071625Z`): grounding **1.00**, fabricated **0**, mandatory
**1.00**, insufficient-rate **1.00**, forced-when-insufficient **0**, rejection-correct **1.00**,
0 operational failures — **no regression** (the grader reads decisions/scores, not ranking, so the
ranking change is orthogonal; extraction-recall 0.79 is upstream gpt-4o noise, no extraction code
touched). `/code-review` (medium) found one downstream display bug — the report podium/narratives
headlined the absolute `total_score` while ranking by the normalised score (a partial-excellent #1
could render *below* #2, delta `+-`); fixed via a shared `_rank_score()` helper in
`app/output/report_builder.py` + `app/agents/explanation.py` (back-compatible).

## Problem (verified against code)

`EvaluationOutput.total_weighted_score` (0–10) = `sum(weighted_contribution) * 10`, where
`weighted_contribution = (raw_score/10) * weight` ([app/agents/evaluation.py:473](../../app/agents/evaluation.py#L473)).
A criterion the agent **could not assess** (`insufficient_evidence=True`) has `raw_score=0` →
`weighted_contribution=0` → it contributes **zero**, indistinguishable from a genuine 0/10.

The comparator ranks vendors **by this raw total** ([app/agents/comparator.py:193-201](../../app/agents/comparator.py#L193-L201)),
and the decision agent labels recommendations from it ([app/agents/decision.py:191](../../app/agents/decision.py#L191)).

**Consequence:** a vendor assessed on only 60% of the criterion-weight, scoring *perfectly* on
all of it, is capped at 6.0 and loses to a fully-assessed vendor who scored a mediocre 6.5. A
vendor that simply *wasn't fully assessed* is treated as if it *failed* the unassessed criteria.
This is a real procurement-fairness bug, not a benchmark artefact. The current code already carries
`BACKLOG E3.d` TODO breadcrumbs in evaluation/comparator/decision.

## Design

Two honest numbers instead of one, both surfaced:

| Field | Meaning | Scale |
|---|---|---|
| `total_weighted_score` (unchanged) | absolute score; un-assessed criteria still count as 0 | 0–10 |
| `coverage` (new) | fraction of total criterion-weight actually assessed | 0–1 |
| `coverage_normalised_score` (new) | quality **over what was assessed**, projected to 0–10 | 0–10 |

`coverage = assessed_weight / total_weight`, where `assessed_weight` sums the weights of
non-`insufficient_evidence` criteria. `coverage_normalised_score = total_weighted_score / coverage`
(when `coverage > 0`; else 0). Maths: with weights summing to 1, this equals the weight-averaged
`raw_score` over the assessed criteria × 1 — i.e. "if we extrapolate observed quality, how good is
this vendor". A fully-assessed vendor has `coverage = 1.0` so `coverage_normalised_score == total_weighted_score`
(no behaviour change for the common case).

### Ranking rule (decision locked 2026-06-02)

Rank by `coverage_normalised_score`, **but** any vendor below a **config** coverage floor is
flagged `low coverage — human review`, never silently trusted. This avoids the "1-of-10 perfect
beats 10-of-10 good" trap without re-introducing the under-ranking.

- New config: `platform.ranking.min_coverage_for_trust` (default **0.5** in `platform.yaml`).
- `ComparatorOutput.low_coverage_vendors`: vendors with `coverage < min_coverage_for_trust`.
- The decision agent adds a per-vendor `review_reason` naming the coverage value, and
  `requires_human_review` is already driven by `review_reasons`.

**No hardcoding:** the floor lives in `platform.yaml`. Nothing cert/insurance/domain-specific —
coverage is computed from generic criterion weights, so it works for any future agent/domain.

## Module-interaction map

| Module | Change | Contract in → out |
|---|---|---|
| `app/config/platform.yaml` + `loader.py` | new `ranking.min_coverage_for_trust: float` | YAML → `settings.platform.ranking` |
| `app/schemas/schema_evaluation.py` | `EvaluationOutput.coverage`, `.coverage_normalised_score`; `ComparatorOutput.low_coverage_vendors` | additive, defaulted (back-compat) |
| `app/schemas/schema_decision.py` | `ShortlistedVendor.coverage`, `.coverage_normalised_score` | additive, defaulted |
| `app/agents/evaluation.py` | compute the two new fields from criterion weights | `EvaluationSetup + facts → EvaluationOutput` |
| `app/agents/comparator.py` | rank by `coverage_normalised_score`; populate `low_coverage_vendors` + warning | `EvaluationOutput[] → ComparatorOutput` |
| `app/agents/decision.py` | recommendation from `coverage_normalised_score`; coverage review-reason | `Evaluation+Comparator → DecisionOutput` |

## Exit criteria (testable)

1. **Coverage maths** — a vendor scored 10/10 on criteria summing to weight 0.6 (rest insufficient)
   has `coverage == 0.6` and `coverage_normalised_score == 10.0`; `total_weighted_score == 6.0`.
2. **No-change invariant** — a fully-assessed vendor (`coverage == 1.0`) has
   `coverage_normalised_score == total_weighted_score` (ranking unchanged for the common case).
3. **Ranking fix** — partial-but-excellent (cov 0.6, norm 10) ranks **above** full-but-mediocre
   (cov 1.0, norm 6.5) in `overall_ranking`.
4. **Low-coverage flag** — a vendor with `coverage < min_coverage_for_trust` appears in
   `ComparatorOutput.low_coverage_vendors` and produces a decision `review_reason`;
   `requires_human_review == True`.
5. **Config-driven** — changing `min_coverage_for_trust` in `platform.yaml` changes the flag set;
   no value hardcoded in agent files.
6. **Measure-first** — full 6-scenario benchmark shows no regression on grounding/fabrication and
   the intended ranking change is visible; full test suite green; contracts 14/14; drift OK.

## Test plan

- **Unit** (`tests/test_coverage_normalised_ranking.py`): coverage maths (criteria 1–4 above) with
  hand-built `EvaluationOutput`/`CriterionScore` objects (no LLM); comparator ranking order; the
  config-threshold flag set; the no-change invariant.
- **Integration**: benchmark runner before/after (`PYTHONUTF8=1 python -m benchmark.runner.run_benchmark`).
- **Regression**: full `pytest` suite + `tools/contract_tests.py` + `tools/drift_detector.py`.
