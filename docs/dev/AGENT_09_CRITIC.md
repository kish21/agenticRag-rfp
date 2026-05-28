# Agent 09 — Critic Agent
**What it does:** Runs after every other agent and acts as an independent quality checker. It does not retrieve anything, generate any text, or make any decisions — its only job is to look at what the previous agent produced and raise a flag if something looks wrong. It is the only agent that can stop the pipeline. Every check is a hard mathematical rule — no LLM is involved anywhere in this agent.

---

## Why a Separate Critic Agent Exists

Without the Critic, errors compound silently. If the Extraction Agent hallucinates a certification that never appeared in the vendor document, the Evaluation Agent scores it, the Comparator ranks on it, and the Decision Agent recommends a vendor based on a fact that did not exist. By the time a human reads the final report, the mistake is buried under six layers of downstream reasoning.

The Critic breaks this chain. It checks the output of each agent before the next one runs. If a grounding quote cannot be found in the source text, the pipeline stops immediately rather than carrying the hallucination forward.

---

## Process Flow

```
Agent X produces output
            │
            ▼
┌─────────────────────┐
│  Critic runs its    │
│  checks for Agent X │
└─────────────────────┘
            │
     ┌──────┴──────┐
     │             │
  HARD flag    SOFT flag     No flags
     │             │             │
  BLOCKED    APPROVED       APPROVED
  (pipeline  _WITH_         (continues)
   stops)    WARNINGS
             (continues
              with flag)
```

---

## Tools Used

| What | Tool | LLM? | Cost |
|---|---|---|---|
| All threshold checks | Python comparison operators (`<`, `>`, `==`) | No | Free |
| Verbatim grounding verification | Python `str.__contains__` with `re.sub(r"\s+", " ")` normalisation | No | Free |
| Count checks | Python `len()`, `any()`, `all()` | No | Free |
| Flag creation | Pydantic `CriticFlag` model construction | No | Free |
| Verdict decision | Python `if/else` on flag severity list | No | Free |

**Zero LLM calls. Zero external API calls. Zero database reads.**

The Critic receives the previous agent's output as a Python object and returns a `CriticOutput` Python object. Nothing is read from or written to any database during the check itself.

---

## Checks Per Agent

### After Ingestion Agent

| Check | Type | Threshold | Action |
|---|---|---|---|
| Document quality score too low | HARD | `quality_score < 0.4` | Block — ask vendor to resubmit as digital PDF |
| Quality score low but acceptable | SOFT | `quality_score < 0.65` | Warn — some sections may not be retrievable |
| Zero requirement_response sections found | HARD | `chunks_by_type["requirement_response"] == 0` | Block — document does not address any RFP requirements |
| Duplicate document submitted | SOFT | `status == "duplicate"` | Warn — skip re-ingestion, use existing data |

---

### After Retrieval Agent

| Check | Type | Threshold | Action |
|---|---|---|---|
| Zero chunks returned (mandatory check) | HARD | `empty_retrieval and is_mandatory` | Block — vendor document does not address this requirement |
| Zero chunks returned (non-mandatory) | SOFT | `empty_retrieval and not is_mandatory` | Warn — widen query or mark as insufficient evidence |
| Low retrieval confidence | SOFT | `confidence < 0.4` | Warn — vendor may not cover this criterion; review manually |
| No answer-bearing chunks found | SOFT | all chunks fail `is_answer_bearing` | Warn — try HyDE retrieval or broaden query |
| All chunks are background sections (mandatory) | SOFT | `all(section_type == "background") and is_mandatory` | Warn — section type filter may be needed |

---

### After Extraction Agent

| Check | Type | Threshold | Action |
|---|---|---|---|
| Grounding quote not found verbatim in source | SOFT | `quote not in source_chunk_text` | Flag each failure for human review |
| Majority of facts fail grounding check | HARD | `grounding_failures > total_facts / 2` | Block — high hallucination risk, do not use extracted facts |
| Low extraction completeness | SOFT | `extraction_completeness < 0.5` | Warn — vendor may not have addressed all requirements |

**Whitespace normalisation:** Before the verbatim check, both the grounding quote and the source chunk are passed through `re.sub(r"\s+", " ", text).strip()`. This handles PDF tables where cells land on separate lines — the LLM joins them with single spaces but the raw text has newlines. Without normalisation, valid quotes would fail the check.

---

### After Evaluation Agent

| Check | Type | Threshold | Action |
|---|---|---|---|
| Mandatory check passed on implicit confirmation only | SOFT | `decision_basis == "implicit_confirmation"` | Warn — mandatory requirements need explicit evidence |
| Contradictory evidence found for a check | HARD | `contradictions_found` is not empty | Block — cannot make reliable decision, human review required |
| High score variance | SOFT | `variance_estimate >= 2.0` | Warn — score may not be reliable, note in report |

---

### After Comparator Agent

| Check | Type | Threshold | Action |
|---|---|---|---|
| No ranking produced | HARD | `overall_ranking` is empty | Block — cannot proceed to Decision Agent |
| Low ranking confidence | SOFT | `ranking_confidence < 0.5` | Warn — ranking may not be reliable |
| Unstable criterion rankings | SOFT | any `rank_stable == False` | Warn — score margins too close for reliable ranking |

---

### After Decision Agent

| Check | Type | Threshold | Action |
|---|---|---|---|
| Vendor rejected without evidence citations | HARD | `evidence_citations == []` for a rejected vendor | Block — legal exposure, cannot reject without evidence |
| All vendors rejected | ESCALATE | `shortlisted == 0 and rejected > 0` | Escalate — requirements may be too restrictive, review with procurement team |

---

### After Explanation Agent

| Check | Type | Threshold | Action |
|---|---|---|---|
| Very low grounding completeness | HARD | `grounding_completeness < 0.70` | Block — report contains too many unverified claims, do not send to customer |
| Moderate grounding completeness | SOFT | `grounding_completeness < 0.90` | Warn — review before sending |
| Many ungrounded claims removed per vendor | SOFT | `ungrounded_claims_removed > 3` | Warn — high hallucination in explanation, check source data quality |
| Claim grounding quote not found in source | HARD | verbatim check fails on any of first 5 claims | Block — hallucination, remove claim from report |

---

## Verdict Levels

| Verdict | Condition | Effect on pipeline |
|---|---|---|
| `APPROVED` | No flags | Continue |
| `APPROVED_WITH_WARNINGS` | Soft flags only | Continue, flags logged and shown in UI |
| `BLOCKED` | Any hard flag | Pipeline stops. `_fail()` called, run marked `blocked` in DB, customer notified |
| `ESCALATED` | Hard flag + "escalate" in recommendation | Pipeline stops, escalated to human reviewer |

---

## LLM Call Summary

**Zero LLM calls anywhere in this agent.**

Every check is a Python rule. This is intentional — if the LLM that produced the output also checks its own output, it will rationalise its own mistakes. The Critic must be independent of the model that produced the data it is checking.

---

## Key Files

| File | Role |
|---|---|
| `app/agents/critic.py` | All 6 critic functions, one per agent |
| `app/schemas/output_models.py` | `CriticOutput`, `CriticFlag`, `CriticVerdict`, `CriticSeverity` |
| `app/api/_evaluation/pipeline.py` | Calls each critic inline after its agent, blocks on hard flags |
| `tools/smoke_test.py` | Calls each critic inline, `sys.exit(1)` on BLOCKED |

---

## Known Limitations (Backlog)

| # | Issue | Backlog item |
|---|---|---|
| 1 | Verbatim grounding check produces false positives when quotes are faithful but differently worded | AI-007 |
| 2 | Answer-bearing quality check is just 2-word overlap — too weak for semantic relevance | AI-007 |
| 3 | No independent cross-chunk contradiction detection — only catches what Evaluation Agent already flagged | AI-007 |

---

## Fixes Applied This Session

Two categories of fixes were made: improvements to the critic checks themselves, and fixes to the pipeline that was silently ignoring the critic's verdicts.

### Fix 1 — Low retrieval confidence now flagged
**What was wrong:** `critic_after_retrieval` only flagged completely empty retrievals. A retrieval that returned 5 chunks with a confidence score of 0.15 out of 1.0 — indicating the vendor document barely addresses this criterion — passed silently as APPROVED. The pipeline had no visibility that the evidence quality was very low.

**Fix:** Added a `low_retrieval_confidence` soft flag in `critic_after_retrieval` when `confidence < 0.4` and results are not empty. The flag message tells the reviewer to check whether the vendor document actually covers this requirement.

---

### Fix 2 — Ingestion critic output was completely discarded in the API pipeline
**What was wrong:** In `app/api/_evaluation/pipeline.py`, both ingestion calls (`run_ingestion_agent`) discarded their return values entirely — the critic output was never captured. A vendor document with quality score 0.2 (far below the 0.4 hard block threshold), or one with zero requirement-response sections, would have proceeded through all 9 agents without the pipeline ever knowing the critic had blocked it.

**Fix:** Both ingestion calls now capture `(output, critics)`. The critics list is iterated and `_block_if_hard()` is called for each — raising a `RuntimeError` that the outer exception handler catches, marks the run as blocked, and notifies the customer.

---

### Fix 3 — Retrieval ran with hardcoded settings, ignoring org configuration
**What was wrong:** The API pipeline called `run_retrieval_agent` with hardcoded parameters: `use_hyde=False`, `n_candidates=10`, `n_final=3`. These values ignored the org_settings entirely — even after `retrieval_top_k` was updated to 20 in the database, the frontend pipeline continued using 10. HyDE was always off regardless of the org's configured preference.

**Fix:** The pipeline now loads org_settings via `get_org_settings(org_id)` at run start and passes `org_settings=org_settings` to `run_retrieval_agent`, which overrides all individual parameters from the DB configuration. The hardcoded values are removed.

---

### Fix 4 — All agent critic outputs were discarded with `_` in the API pipeline
**What was wrong:** Every agent call in the pipeline used `output, _ = await run_agent(...)` — the `_` silently discarded the critic output. This meant:
- Evaluation critics showing contradictory evidence (hard block) were ignored
- Comparator critics showing an empty ranking (hard block) were ignored
- Decision critics catching vendor rejection without evidence (hard block, legal exposure) were ignored
- Explanation critics catching hallucinated report claims (hard block) were ignored

**Fix:** All agent calls now capture their critic output by name (`ev_critic`, `comp_critic`, `dec_critic`, `exp_critic`). Soft flags are logged to the run's audit trail via `rfp_logger`. Hard flags call `_block_if_hard()` which raises a `RuntimeError` that stops the run.

---

### Fix 5 — Step 9 "Critic" was a fake emit
**What was wrong:** The pipeline had a "Step 9 — Critic" section that consisted entirely of:
```python
_emit("critic", "done", "All agent outputs validated")
```
No checks ran. No verdicts were read. It unconditionally emitted "passed" regardless of what had actually happened in the run. The frontend showed a green Critic step even when all prior critics had raised soft warnings.

**Fix:** Step 9 now collects all critic outputs from the run, counts the total soft flags across all agents, and emits an accurate summary message. Hard blocks are now raised inline after each agent so they can never reach Step 9 anyway.
