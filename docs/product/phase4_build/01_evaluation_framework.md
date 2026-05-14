# Evaluation Framework
*Version 1.0 — 2026-05-14*

---

## Purpose

This document defines how the platform measures the quality of its AI outputs — not whether the software runs, but whether the outputs are correct, grounded, and useful.

This is distinct from the test plan (which tests code) and the checkpoint system (which tests integration). This document defines the AI quality metrics.

---

## 1. Retrieval Quality

### Metrics

| Metric | Definition | Target | Measurement |
|---|---|---|---|
| Retrieval Adequacy Rate | % of criteria where the Retrieval Critic judges chunks as adequate | > 90% | Retrieval Critic `adequate` field |
| Chunk Relevance@5 | % of top-5 reranked chunks that contain the sought fact | > 80% | Manual annotation on 50-doc test set |
| MRR@10 (Mean Reciprocal Rank) | Average reciprocal rank of first relevant chunk in top-10 | > 0.7 | Annotated test set |
| HyDE Lift | Improvement in Retrieval Adequacy Rate when HyDE is enabled vs. disabled | > 5% | A/B: 20 criteria with/without HyDE |
| Reranker Lift | Improvement in Chunk Relevance@5 from BM25/dense → reranked | > 15% | A/B: 20 criteria with/without reranker |

### Test Set

- 5 vendor response PDFs (mix of real and synthetic), 50–200 pages each
- 12 criteria per evaluation (certifications, insurance, SLA, pricing, references)
- 60 criterion-vendor pairs total
- Ground truth: manually annotated — which page and chunk contains the correct answer

### How to Run

```bash
python tests/evaluation/retrieval_eval.py --test-set tests/data/retrieval_test_set.json
```

---

## 2. Extraction Accuracy

### Metrics

| Metric | Definition | Target | Measurement |
|---|---|---|---|
| Grounding Rate | % of facts where `grounding_quote` is verbatim in source | 100% | Critic hard check — any failure = 0% |
| Extraction Accuracy | % of facts with correct type + value vs. ground truth | > 95% | Annotated test set |
| False Positive Rate | % of facts extracted that do not exist in source | < 2% | Annotated test set |
| Hallucination Block Rate | % of adversarial runs where Critic blocks hallucinated fact | > 95% | Red team test set |
| Whitespace Normalisation Pass | % of PDF table-format facts that pass grounding check | 100% | Regression test (PDF table fixture) |

### Red Team Test Set

50 deliberately injected hallucinations:
- Fabricated certificate numbers (e.g., ISO 27001 cert number "XYZ-99999" that does not appear in the PDF)
- Wrong insurance type (extracted PI when source says PL)
- Wrong coverage amount (£10M extracted when source says £5M)
- Date transposition (expiry year swapped)

All 50 should be caught by the Extraction Critic or grounding check.

### How to Run

```bash
python tests/evaluation/extraction_eval.py --test-set tests/data/extraction_test_set.json
python tests/evaluation/red_team_eval.py --adversarial tests/data/red_team_injections.json
```

---

## 3. Evaluation Scoring Quality

### Metrics

| Metric | Definition | Target | Measurement |
|---|---|---|---|
| Score Consistency | Same vendor + same docs → same score across 5 runs | Variance < 0.05 | Run 5× with temperature=0.1 |
| Score Calibration | Does the score correlate with human expert scores? | Pearson r > 0.85 | Expert annotation of 20 evaluations |
| Confidence Calibration | Is the confidence score correlated with actual accuracy? | Calibration error < 0.1 | Calibration curve on test set |
| Coverage | % of criteria with at least one evidence citation | 100% | Critic check on evaluation output |

---

## 4. Comparator & Decision Quality

### Metrics

| Metric | Definition | Target | Measurement |
|---|---|---|---|
| Rank Stability | Same documents → same vendor ranking across 5 runs | 100% match | 5× runs on identical inputs |
| Rank Agreement with Expert | Does AI ranking match expert panel ranking? | > 80% agreement | Expert annotation of 10 multi-vendor RFPs |
| Approval Tier Accuracy | Is the correct approval tier triggered for the contract value? | 100% | Automated: 3 contract value bands × 10 test cases |

---

## 5. Explanation / Report Quality

### Metrics

| Metric | Definition | Target | Measurement |
|---|---|---|---|
| Citation Coverage | % of claims in report that have a source citation | 100% | Critic hard check |
| Grounding Faithfulness | % of cited claims where the cited chunk supports the claim | > 95% | Manual review of 20 reports |
| Readability | Mean reading time for Department Head to review report | < 15 minutes | User research (simulated) |

---

## 6. End-to-End Pipeline Quality

### Metrics

| Metric | Definition | Target | Measurement |
|---|---|---|---|
| Pipeline Success Rate | % of runs that complete without HARD block | > 98% | Production monitoring |
| HARD Block Rate | % of runs where Critic issues a HARD block | < 2% | LangFuse critic flag log |
| SOFT Block Rate | % of runs where Critic issues a SOFT warning | < 10% | LangFuse critic flag log |
| False Hard Block Rate | % of HARD blocks that were incorrect (human overrides and confirms original) | < 1% | Override audit log |
| End-to-End Latency (3 vendors) | Time from upload to PDF report available | < 45 minutes | Timed production runs |

---

## 7. LLM Provider Parity

When a new LLM provider is added or switched, run the parity test:

```bash
python tests/evaluation/provider_parity.py \
  --provider-a openai \
  --provider-b modal \
  --test-set tests/data/extraction_test_set.json
```

Expected: Extraction accuracy within 5%, Critic pass rate within 5%, Rank order agreement > 80%.

---

## 8. Evaluation Cadence

| When | What to run |
|---|---|
| After every code change to agent files | `python tests/evaluation/retrieval_eval.py` + `extraction_eval.py` |
| After provider change (LLM, embedding, reranker) | Full evaluation suite + provider parity test |
| Before pilot customer deployment | Full suite + red team + expert annotation |
| Monthly in production | End-to-end latency + success rate from LangFuse dashboard |
