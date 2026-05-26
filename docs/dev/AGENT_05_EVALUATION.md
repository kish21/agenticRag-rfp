# Agent 04 — Evaluation Agent

## What it does (plain English)

After the Extraction Agent has saved structured facts to the database, the Evaluation Agent reads those facts and produces two things:

1. **Compliance decisions** — a pass/fail/not-enough-info verdict for every mandatory requirement. For example: "Does this vendor hold ISO 27001?" → Pass. "Do they have £5M professional indemnity insurance?" → Fail.

2. **Criterion scores** — a 0–10 score for every weighted scoring criterion, using a rubric the customer defined at setup. For example: "Security posture" with rubric "9–10: holds ISO 27001 + Cyber Essentials; 6–8: holds one of the two..." → Score: 8.

The total weighted score across all criteria is what the Comparator Agent uses to rank vendors against each other.

---

## Step-by-step process

```
1. Load extracted facts from PostgreSQL for this vendor + run
2. For each mandatory check:
   a. Find the relevant facts from the right category
   b. Ask LLM: pass / fail / insufficient_evidence?
   c. If no facts OR fails AND extraction wasn't already retried:
      → Fallback: search Qdrant directly, verify each chunk with LLM
      → If chunk evidence found, upgrade decision to pass
3. For each scoring criterion:
   a. Find the relevant facts from the linked extraction targets
   b. Ask LLM to apply the customer's rubric → 0-10 score
   c. Multiply by criterion weight → weighted contribution
4. Calculate overall compliance (fail > review_required > pass)
5. Sum all weighted contributions → total vendor score
6. Run Critic check
```

---

## Key design rules

| Rule | Why |
|------|-----|
| Reads facts from PostgreSQL, never Qdrant directly | Structured facts = deterministic evaluation. Same facts in → same scores out. Temperature 0.0. |
| Fallback to Qdrant only when facts are missing | If extraction missed something, the evaluation agent tries harder rather than silently returning "insufficient evidence" |
| Extraction retry flag prevents loops | If the extraction critic already retried a fact type, the evaluation agent will not trigger a second Qdrant fallback for it — avoids spinning |
| Missing facts score 0 with a warning | No silent score inflation from unrelated facts |
| All 3 LLM calls use externalised prompts | System prompts are in YAML files and LangSmith Hub — can be updated without code change |

---

## Fallback mechanism

When a mandatory check has no extracted facts, the agent:
1. Runs a fresh Qdrant retrieval using `what_passes` text as the query (more specific than the check name)
2. If retrieval confidence is low, retries once with hybrid+HyDE search and doubled top-K
3. Verifies each returned chunk individually with the LLM ("does this text satisfy ALL conditions?")
4. If any chunk confirms the requirement, the decision is upgraded to **pass** with confidence 0.75

This means a vendor is not penalised just because the extraction step missed a fact — the evaluation agent will search harder before giving up.

---

## Scoring

Each criterion has a 4-band rubric defined by the customer at setup:

| Band | Meaning |
|------|---------|
| 9–10 | Exceeds requirement — full evidence, best-in-class |
| 6–8  | Meets requirement — solid evidence, minor gaps |
| 3–5  | Partial compliance — some evidence, notable gaps |
| 0–2  | Fails or no evidence |

The LLM applies the rubric strictly at temperature 0.0. The raw score (0–10) is multiplied by the criterion weight to give a weighted contribution. All contributions are summed into a single `total_weighted_score` for the vendor.

---

## Overall compliance

The agent collapses all mandatory check decisions into a single status:

| Status | When |
|--------|------|
| `pass` | All mandatory checks pass |
| `review_required` | At least one check returned insufficient_evidence |
| `fail` | At least one check failed outright |

`fail` takes priority over `review_required`, which takes priority over `pass`.

---

## Files

| File | Role |
|------|------|
| `app/agents/evaluation.py` | Main pipeline — all evaluation logic |
| `app/db/fact_store.py` | `get_vendor_facts()` — reads structured facts from PostgreSQL |
| `app/prompts/evaluation/verify_threshold.yaml` | System prompt: chunk verification for fallback |
| `app/prompts/evaluation/evaluate_check.yaml` | System prompt: mandatory check pass/fail |
| `app/prompts/evaluation/score_criterion.yaml` | System prompt: rubric scoring |

---

## What was wrong (and fixed in May 2026)

### 1. JSON crashes not handled — CRITICAL
**Before:** All three LLM calls used `json.loads(raw)` with no error handling. If the LLM returned anything malformed (extra text before the JSON, a truncated response), the whole evaluation would crash and that vendor would get no score at all.

**Fix:** All three parse calls now have `try/except json.JSONDecodeError` with safe defaults — a failed parse returns insufficient_evidence or a zero score with a clear rationale, and the run continues.

### 2. Score conversion crash on float values — HIGH
**Before:** `int(parsed.get("raw_score") or 0)` — if the LLM returned `7.5` as a JSON number, Python's `int()` cannot convert a float string and throws ValueError.

**Fix:** `int(float(parsed.get("raw_score") or 0))` — converts via float first, so `7.5` becomes `7`.

### 3. Unrelated facts sent to scoring criteria — MEDIUM
**Before:** When no specific facts were found for a scoring criterion, the code fell back to sending ALL extracted facts (certifications, pricing, projects, insurance, everything) to the LLM. A data security criterion could be scored 7/10 because the vendor had an impressive list of past projects — nothing to do with security.

**Fix:** When no targeted facts are found, the criterion is scored with an empty context and a warning is added to `evaluation_warnings`. The LLM will apply the 0–2 rubric band and give a low-confidence score, which accurately reflects that no relevant evidence was found.

### 4. All LLM system prompts were inline strings — LOW
**Before:** The system prompts for all three LLM calls were hardcoded Python strings — not versionable, not editable without a code deployment.

**Fix:** All three moved to `app/prompts/evaluation/` YAML files, registered in the prompt registry, and pushed to LangSmith Hub for live editing.

### 5. Null evidence_used caused Pydantic validation errors — LOW
**Before:** `parsed.get("evidence_used", [])` — if the LLM returned `"evidence_used": null`, this would pass `None` to the Pydantic model, causing a validation error.

**Fix:** `(parsed.get("evidence_used") or [])` — treats both missing and null as an empty list.
