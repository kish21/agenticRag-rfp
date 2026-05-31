# E3 — Evidence-Quality Benchmark

A repeatable, ground-truth benchmark that measures how well the RFP-evaluation
pipeline retrieves evidence, extracts facts, **cites them honestly**, scores
criteria, and handles missing/conflicting evidence — with reproducible numbers.

Contract & exit criteria: [`docs/dev/E3_EXIT_CRITERIA.md`](../docs/dev/E3_EXIT_CRITERIA.md).

## Why you can trust the numbers (integrity model)

1. **Ground truth by construction.** Scenarios are synthetic documents we author
   (`generation/build_scenarios.py`). The *same* sentence is written into the PDF
   and recorded as the golden `grounding_substring` — so the answer key is not a
   human's fuzzy judgement, it's what we literally put in the document.
2. **The answer key is itself grounded.** `tests/test_benchmark_dataset.py` (A2)
   asserts every present fact's grounding substring appears verbatim in its PDF,
   read with the *pipeline's own* extractor. If that fails, no number is trusted.
3. **Pure, tested metric math.** Everything in `metrics/` is a pure function
   (no DB/LLM/IO), unit-tested in CI (`tests/test_benchmark_metrics.py`). The
   only impure code is `runner/` (it runs the real pipeline).
4. **No hand-entered numbers.** The committed artifact records the git commit,
   model/config, and per-scenario raw outputs; every figure is recomputed by the
   runner. The runner **fails loud** (non-zero exit, `failures[]`) rather than
   silently skipping a scenario.

## Layout

```
golden_schema.py     typed answer key (ScenarioGolden)
generation/          pdf_builder.py + build_scenarios.py (single source)
scenarios/<id>/      rfp.pdf · vendor PDF · setup.json (fixed EvaluationSetup) · golden.json
metrics/             retrieval · extraction · grounding · scoring · runtime_cost · aggregate (pure)
runner/              pipeline_adapter (state_to_actual = pure; run_scenario = impure) · run_benchmark CLI
results/             committed results_<UTC>.json + .md artifacts
```

## Scenarios (6)

`01_clean` · `02_table_heavy` · `03_long` (buried facts) · `04_short` (partial
evidence → insufficient) · `05_conflicting` (£10M vs £2M → cannot confirm) ·
`06_missing_evidence` (mandatory omitted → reject). Scanned/OCR is deferred
(needs the Modal OCR path; see the contract).

## Metrics

Retrieval recall@k · extraction precision/recall per fact type · **grounding/
citation accuracy** (+ fabricated-citation count) · scoring band agreement ·
**insufficient-evidence rate** (the no-forced-score promise) · mandatory accuracy
· rejection correctness · score consistency (stdev over repeats) · runtime · cost
· failure rate.

## Running it

Regenerate the synthetic dataset (only when scenarios change — PDFs are committed):

```
python -m benchmark.generation.build_scenarios
```

Run the benchmark (spends API budget — runs the real pipeline; needs Postgres +
Qdrant + an LLM key):

```
python -m benchmark.runner.run_benchmark                 # all scenarios
python -m benchmark.runner.run_benchmark --scenario 01_clean --repeats 3
```

Writes `results/results_<UTC>.json` (+ `.md`). This is **baseline-first**: it
reports numbers and only fails on operational errors, not on a metric being
"too low" (regression gates come once a baseline exists — see the contract).

Dev-box caveat: the BGE reranker requires HuggingFace egress, which the Norton
MITM proxy blocks here, so it falls back to vector-score order. Recorded in the
results so the numbers are interpreted correctly.
