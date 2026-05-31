# E3 — Evidence-Quality Benchmark: Exit-Criteria Contract

**Status:** DRAFT for sign-off (set before any build, 2026-05-31)
**Why this doc exists:** This is the contract we hold the E3 work to. Every claim
the benchmark makes must trace to a committed artifact and a reproducible run —
so if a later change (or a model) drifts or fabricates a number, it is caught
here against a written standard, not against memory.

---

## Vision this serves

> Evidence-grounded, audit-ready vendor evaluation for regulated procurement.

The product's core promise is that **every claim is backed by a verbatim source
citation**, and that the system **never fabricates evidence or forces a score
where there is none**. E3's job is to **prove that promise with reproducible
numbers** — and to make the rare "we don't have enough evidence" case explicit
and visible rather than hidden behind a fabricated 0.

---

## Definitions (so terms can't drift)

- **Ground truth by construction:** every expected fact is something we
  deliberately wrote into (or left out of) a synthetic PDF. No human "judging"
  of fuzzy outputs — the answer key is authored, not interpreted.
- **Grounding accuracy:** fraction of extracted facts whose `grounding_quote`
  maps to **real verbatim source text** (whitespace-normalised) — i.e. the
  citation is honest, not invented. This is the anti-hallucination metric.
- **Insufficient evidence:** an explicit state meaning "the document does not
  support a score/decision here." Distinct from a genuine low score.

---

## Exit criteria

Each item is binary (met / not met) and has a **verified-by** that anyone can
re-run. A criterion is NOT "done" on assertion — only when its verified-by passes.

### A — Benchmark dataset (the answer key)

| ID | Criterion | Verified by |
|----|-----------|-------------|
| A1 | ≥6 synthetic scenarios committed: `clean`, `table_heavy`, `long`, `short`, `conflicting`, `missing_evidence`. Each has an RFP PDF + ≥1 vendor PDF + criteria + a `golden.json` validating against `ScenarioGolden`. | `benchmark/scenarios/*/` exist; a loader validates every `golden.json`. |
| A2 | **Ground-truth integrity:** every `present` golden fact's `grounding_substring` appears **verbatim (whitespace-normalised) in its source PDF**. (If our own answer key isn't grounded, no downstream number is trustworthy.) | A checker script asserts each substring is found in the extracted PDF text; runs in CI. |
| A3 | Coverage of the hard cases: ≥1 scenario omits a mandatory item; ≥1 has internally conflicting evidence; ≥1 buries facts in a long doc; ≥1 presents facts only in tables. | The four scenarios above exist with golden files encoding those expectations. |

### B — Metrics computed (all families, per scenario + aggregate)

| ID | Criterion | Verified by |
|----|-----------|-------------|
| B1 | **Retrieval recall@k** — did retrieval surface chunks covering each present fact's grounding text? | `benchmark/metrics/retrieval.py` + unit test; number in results artifact. |
| B2 | **Extraction precision & recall**, per fact type — extracted facts matched against golden present/absent facts. | `benchmark/metrics/extraction.py` + unit test; numbers in artifact. |
| B3 | **Grounding / citation accuracy** — fraction of extracted facts with an honest verbatim citation; **fabricated-citation count reported separately**. | `benchmark/metrics/grounding.py` + unit test; numbers in artifact. |
| B4 | **Scoring consistency** — variance of `raw_score` across N≥3 repeat runs per criterion (determinism), and agreement with golden expected band where given. | `benchmark/metrics/scoring.py` + unit test; numbers in artifact. |
| B5 | **Runtime, cost, failure rate** — per-stage wall-clock, total USD (via `RunCostAccumulator`), and % of vendor-evaluations that blocked, per stage. | `benchmark/metrics/runtime_cost.py`; numbers in artifact. |
| B6 | **Insufficient-evidence rate** — for facts/checks the golden marks absent, the fraction the system correctly resolved to `insufficient_evidence` vs forced a score/pass. | `benchmark/metrics/scoring.py` + `grounding.py`; numbers in artifact. |

### C — Repeatability & integrity (the anti-drift guarantees)

| ID | Criterion | Verified by |
|----|-----------|-------------|
| C1 | **One command** runs the full benchmark and writes a timestamped `results_<date>.json` **and** a human-readable `metrics.md`. | `python -m benchmark.runner.run_benchmark` produces both. |
| C2 | **No hand-entered numbers.** Every metric in the committed artifact is computed by the runner from real pipeline outputs + golden files. The artifact records the **git commit, model/config, and per-scenario raw outputs**, so any number is traceable. | Artifact schema includes `commit`, `config`, `per_scenario` raw; reviewer can recompute. |
| C3 | **Fail loud.** If a scenario errors or a golden file is invalid, the runner records a failure and exits non-zero — it never silently skips a scenario or drops a metric. | Runner exit code + a `failures[]` list; tested. |
| C4 | **Pure, CI-tested metrics.** All `benchmark/metrics/*` functions are pure (no DB/LLM/IO) and covered by deterministic unit tests that run in CI without API spend. | `tests/test_benchmark_metrics.py` green in CI. |

### D — Product change: no forced scores

| ID | Criterion | Verified by |
|----|-----------|-------------|
| D1 | The evaluation output can represent **insufficient evidence** for a scoring criterion distinctly from a real `0`; a criterion with no evidence is **not folded into the ranking as a fabricated 0**. | Schema field + evaluation-agent logic; unit test on the `missing_evidence` scenario. |
| D2 | Comparator, decision, and explanation handle the insufficient state correctly (no crash, not silently treated as 0). | Pipeline runs the `missing_evidence` scenario end-to-end; benchmark green. |
| D3 | The **frontend surfaces** low-confidence / insufficient-evidence to the user (a visible state, not hidden). Built via the UI skills (`/frontend-design` → `/frontend-component` → `/anti-ai-ui`). | UI renders the state; screenshot/described in PR. |

### E — Documentation

| ID | Criterion | Verified by |
|----|-----------|-------------|
| E1 | `docs/dev/PERFORMANCE_AND_QUALITY_METRICS.md` updated with the **measured baseline numbers**, dated and tied to the git commit that produced them. | The doc cites the committed `results_<date>.json`. |
| E2 | A reviewer note documents the methodology + the integrity guarantees (A2/C1–C4). | `benchmark/README.md`. |

---

## DECISION (signed off 2026-05-31) — baseline first

This first run **records** the measured numbers as the documented baseline, with
**no hard pass/fail gate**. Once real numbers exist, regression gates (e.g.
"grounding accuracy must stay ≥ X") are set in a follow-up — you can't set an
honest threshold before measuring. The runner therefore reports numbers and only
*fails* on operational errors (C3), never on a metric being "too low" in this pass.

---

## Explicitly OUT of scope for E3 (so scope can't silently creep)

- Scanned/OCR scenario — **deferred (signed off 2026-05-31)**; depends on the
  Modal OCR path which doesn't run on the dev box. Add when that path is runnable.
- Per-PR CI gate that calls real LLMs — too costly/flaky; the benchmark is an
  on-demand runner that commits an artifact (only the pure metric tests run per-PR).
- Tuning retrieval/extraction to hit a target — E3 *measures*; improving the
  numbers is separate work informed by what E3 reveals.
