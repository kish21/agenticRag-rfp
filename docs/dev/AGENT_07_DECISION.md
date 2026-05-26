# Agent 06 — Decision Agent

## What it does (plain English)

After all vendors have been ranked by the Comparator Agent, the Decision Agent makes the final accept/reject call for each vendor and routes the shortlist to the right person for approval.

It answers three questions:
1. **Who is rejected?** — any vendor with an outright FAIL on a mandatory check
2. **Who is shortlisted?** — everyone else, ordered by their total weighted score
3. **Who needs to approve?** — based on the contract value, routes to department head / regional director / CFO / board

It also escalates if every vendor was rejected, or flags shortlisted vendors who still have unresolved "we couldn't find evidence" checks — so the approver knows before they sign off.

---

## Where it sits in the pipeline

```
Evaluation Agent  →  produces compliance decisions + criterion scores
       ↓
Comparator Agent  →  produces overall_ranking + ranking_confidence
       ↓
Decision Agent    →  reads both, produces shortlist + rejections + approval routing
       ↓
Explanation Agent →  reads Decision output, writes the human-readable report
```

---

## Step-by-step process

```
1. For each vendor in evaluation_outputs:
   a. If any mandatory check = FAIL → build a RejectionNotice with evidence
   b. Otherwise → add to shortlist candidates
2. Sort shortlist using comparator_output.overall_ranking order
3. For each shortlisted vendor:
   a. Assign rank and recommendation label (strongly_recommended / recommended / acceptable / marginal)
   b. Check for any insufficient_evidence mandatory checks → add review reason
4. Route to approval tier based on contract value (read from platform.yaml)
5. If all vendors rejected → escalate, set requires_human_review = true
6. Critic check
```

---

## Approval tiers (config-driven)

Tiers are defined in `app/config/platform.yaml` under `governance.approval_tiers`. No hardcoded values in the agent.

| Tier | Approver | Max contract value | SLA |
|------|----------|--------------------|-----|
| 1 | Department Head | £100,000 | 24 hours |
| 2 | Regional Director | £500,000 | 48 hours |
| 3 | CFO | £1,000,000 | 72 hours |
| 4 | Board | No limit | 120 hours |

---

## Recommendation labels (config-driven)

Also defined in `platform.yaml` under `governance.recommendation_thresholds`. Based on the vendor's total weighted score (0–10 scale):

| Score | Label |
|-------|-------|
| 8.0+ | strongly_recommended |
| 6.0+ | recommended |
| 4.0+ | acceptable |
| 0.0+ | marginal |

---

## RejectionNotice and evidence

Every rejected vendor gets a `RejectionNotice` with:
- Which mandatory checks failed
- The reasoning for each failure
- Verbatim evidence citations

If the evaluation did not produce explicit evidence citations (e.g. the vendor simply had nothing to cite), the agent asks the LLM to extract verbatim phrases from the rejection reasoning. The Critic will hard-block the pipeline if a rejection still has no citations — a vendor cannot be rejected without documented evidence.

---

## Files

| File | Role |
|------|------|
| `app/agents/decision.py` | Main pipeline |
| `app/config/platform.yaml` | `governance.approval_tiers` + `governance.recommendation_thresholds` |
| `app/config/loader.py` | `PlatformGovernanceTier`, `PlatformGovernance` Pydantic models |
| `app/prompts/decision/extract_evidence.yaml` | System prompt for evidence extraction fallback |

---

## What the Critic checks

| Check | Severity | What it catches |
|-------|----------|----------------|
| `rejection_without_evidence` | HARD | Vendor rejected with no evidence_citations — legal exposure |
| `all_vendors_rejected` | HARD | Everyone rejected — escalates to human review |
| `shortlisted_vendor_unresolved_checks` | SOFT | Shortlisted vendor has insufficient_evidence on a mandatory check |

---

## What was wrong (and fixed in May 2026)

### 1. Governance tiers hardcoded in agent file — CRITICAL
**Before:** `_DEFAULT_TIERS` was a Python list constant hardcoded directly in `decision.py`. The comment said "override via EvaluationSetup governance config if present" but the function never accepted an `EvaluationSetup` parameter — the override was never possible. CLAUDE.md explicitly prohibits hardcoded thresholds in agent files.

**Fix:** Tiers moved to `app/config/platform.yaml` under `governance.approval_tiers`. `PlatformGovernanceTier` and `PlatformGovernance` models added to `loader.py`. Agent reads from `settings.platform.governance.approval_tiers`.

### 2. Recommendation thresholds hardcoded in agent file — CRITICAL
**Before:** `_RECOMMENDATION_MAP` was a Python constant in `decision.py` with hardcoded 8.0 / 6.0 / 4.0 / 0.0 score thresholds.

**Fix:** Moved to `platform.yaml` under `governance.recommendation_thresholds`. Agent reads from `settings.platform.governance.recommendation_thresholds`.

### 3. LLM evidence extraction returned wrong JSON shape — HIGH
**Before:** The prompt asked the LLM to "return a JSON array" but `response_format={"type": "json_object"}` forces the LLM to return an object, never an array. The code then did `list(parsed.values())` which could produce `[["quote1", "quote2"]]` — a list containing a list — instead of `["quote1", "quote2"]`. Rejection notices could have malformed evidence.

**Fix:** Prompt now asks for `{"evidence": ["quote1", "quote2"]}`. Code parses `parsed.get("evidence") or []` with an `isinstance(c, str)` guard on each item.

### 4. `import json` inside function body — LOW
**Before:** `import json` was inside `_build_rejection_notice`, executed on every call.

**Fix:** Moved to the top of the file.

### 5. No warning for shortlisted vendors with unresolved checks — MEDIUM
**Before:** A vendor with `insufficient_evidence` on a mandatory check was silently shortlisted with no indication to the approver. They could award a contract without knowing a key requirement was never confirmed.

**Fix:** For each shortlisted vendor, any `insufficient_evidence` compliance decision adds a `review_reason` to the output. `requires_human_review` is set to `True`. The Critic raises a soft flag (`shortlisted_vendor_unresolved_checks`) so it appears in the report.
