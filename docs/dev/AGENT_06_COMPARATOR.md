# Agent 05 — Comparator Agent

## What it does (plain English)

After every vendor has been individually evaluated and scored, the Comparator Agent looks at all vendors side by side and produces a ranked list. It answers the question: "Given everything we know, which vendor is best, second, third?"

It does two things:

1. **Per-criterion comparison** — for each scoring criterion (e.g. "Security posture", "SLA reliability"), it looks at every vendor's score and asks the LLM to write a short phrase explaining what makes each vendor stand out or fall short on that specific dimension.

2. **Overall ranking** — sorts all vendors by their total weighted score. This is pure maths — the LLM has no say in the final order. It also calculates the gap between each vendor and the one above it, so you can see whether first place is a clear winner or too close to call.

---

## Step-by-step process

```
1. Check all requested vendors have evaluation outputs — warn for any that are missing
2. Build a score lookup: vendor → criterion → raw_score + evidence
3. For each scoring criterion:
   a. Collect every vendor's score and evidence phrases
   b. Ask LLM to identify what differentiates vendors on this criterion
   c. Record whether rankings are stable (no two vendors within 5% of each other)
4. Sort vendors by total_weighted_score — deterministic, no LLM
5. Calculate rank margins (score gap between each vendor and the one above)
6. Run Critic check
```

---

## Key design rules

| Rule | Why |
|------|-----|
| Final ranking is pure maths, not LLM | The LLM writes human-readable summaries only; the actual order is deterministic and auditable |
| Evidence comes from EvaluationOutput, not re-queried from DB | Facts were already extracted and scored — no need to re-read them |
| Missing vendors cause an explicit warning | Callers know exactly why a vendor is absent from the ranking |
| Rank stability is tracked per criterion | Margins too close to call are flagged so the report can note uncertainty |

---

## Rank stability

For each criterion comparison, the agent checks whether any two adjacent vendors have scores within 5% of each other. If so, the ranking for that criterion is marked `rank_stable = False`.

The Critic surfaces this as a soft warning — narrow margins mean small differences in evidence could have flipped the order, so the report should note the uncertainty rather than presenting it as definitive.

---

## Files

| File | Role |
|------|------|
| `app/agents/comparator.py` | Main pipeline |
| `app/prompts/comparator/compare_criterion.yaml` | System prompt for per-criterion differentiator analysis |
| `app/schemas/output_models.py` | `ComparatorOutput`, `CriterionComparison`, `VendorCriterionComparison` |

---

## What the Critic checks

| Check | Severity | What it catches |
|-------|----------|----------------|
| `empty_ranking` | HARD | No vendors in ranking at all — blocks Decision Agent |
| `vendors_missing_from_ranking` | HARD | One or more requested vendors absent — ranking is incomplete |
| `low_ranking_confidence` | SOFT | Average comparison confidence below 0.5 — note in report |
| `unstable_criterion_rankings` | SOFT | Score margins too narrow on one or more criteria |

---

## What was wrong (and fixed in May 2026)

### 1. JSON crash not handled — CRITICAL
**Before:** `json.loads(raw)` with no error handling in `_compare_criterion`. A single malformed LLM response would crash the comparison for that criterion entirely.

**Fix:** `try/except json.JSONDecodeError` — a bad response returns empty differentiators and zero confidence; the run continues and the caller sees a warning.

### 2. Wasted database calls on every run — MEDIUM
**Before:** At the start of `run_comparator_agent`, the code loaded all vendors' raw facts from PostgreSQL into `all_facts`. This fired N database queries (one per vendor). `all_facts` was never referenced again — the comparisons use the evidence already stored inside the `EvaluationOutput` objects passed in as arguments.

**Fix:** Removed the `all_facts` block entirely. No behaviour change; N fewer DB round-trips per run.

### 3. Missing vendors silently dropped from ranking — MEDIUM
**Before:** If a vendor's evaluation had failed (e.g. extraction crashed), that vendor simply would not appear in `evaluation_outputs`. The agent would produce a ranking with fewer vendors than requested and emit no warning. The caller had no way to know the ranking was incomplete.

**Fix:** At the start of the run, the agent checks every `vendor_id` against `evaluation_outputs` and emits a warning for each missing one. The Critic now also raises a HARD flag (`vendors_missing_from_ranking`) which blocks the Decision Agent from proceeding with an incomplete field.

### 4. System prompt was an inline string — LOW
**Before:** The `_compare_criterion` system prompt was a hardcoded Python string — not versionable, not editable without a code deployment.

**Fix:** Moved to `app/prompts/comparator/compare_criterion.yaml`, registered in the prompt registry, pushed to LangSmith Hub.
