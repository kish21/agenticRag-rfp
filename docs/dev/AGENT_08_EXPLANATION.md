# Agent 07 — Explanation Agent

## What it does (plain English)

This is the final agent in the pipeline. After the Decision Agent has made the accept/reject call for every vendor, the Explanation Agent writes the formal procurement report that gets sent to the approver.

For each vendor — whether shortlisted or rejected — it produces:
- An executive summary (2–3 sentences)
- A compliance narrative (what mandatory checks passed, failed, or were unresolved)
- A scoring narrative (how the vendor performed across the criteria)
- A recommendation rationale (why they are ranked where they are)
- A list of grounded claims — every factual statement backed by a verbatim quote from the vendor's own document

Any claim the LLM writes that cannot be verified word-for-word against the source is removed before the report is published. The approver only sees claims that can be traced directly back to what the vendor actually submitted.

---

## Where it sits in the pipeline

```
Decision Agent  →  shortlist + rejections + approval routing
      ↓
Explanation Agent  →  reads all prior outputs, writes the human-readable report
      ↓
Critic Agent  →  verifies grounding completeness, blocks if too many claims unverifiable
```

---

## Step-by-step process

```
1. For each vendor (both shortlisted and rejected):
   a. Filter source chunks to this vendor's chunks only
   b. Build fact context from extracted facts (all types including custom)
   c. Build compliance summary from evaluation decisions
   d. Ask LLM to generate narrative sections with grounded claims
   e. For each claim: verify grounding_quote appears verbatim in source chunk
   f. Remove any claim that fails verification, count removed claims
2. Compute grounding_completeness = verified claims / total attempted claims
3. Build overall executive summary (shortlist count, top vendor, approval tier)
4. Critic check — hard-blocks if grounding completeness < 70%
```

---

## Grounding verification

Every claim the LLM writes must include:
- `claim_text` — what is being asserted
- `grounding_quote` — the exact phrase from the source document
- `source_chunk_id` — which chunk the quote came from

The verification is **programmatic, not LLM** — the quote is checked with whitespace-normalised string containment against the actual source chunk. If the quote cannot be found verbatim, the claim is silently removed from the report.

This means the report is self-auditing: every sentence that appears in the final output can be traced to a specific location in the vendor's submitted document.

---

## Grounding completeness thresholds (Critic)

| Score | Verdict |
|-------|---------|
| ≥ 90% | Approved |
| 70–89% | Approved with warnings |
| < 70% | HARD BLOCK — report not published |
| 0% (zero claims) | HARD BLOCK — LLM produced nothing verifiable |

---

## Files

| File | Role |
|------|------|
| `app/agents/explanation.py` | Main pipeline |
| `app/prompts/explanation/generate_narrative.yaml` | System prompt for narrative generation |
| `app/schemas/output_models.py` | `ExplanationOutput`, `VendorNarrative`, `GroundedClaim`, `SynthesisLLMResponse` |

---

## What the Critic checks

| Check | Severity | What it catches |
|-------|----------|----------------|
| `low_grounding_completeness` | HARD | < 70% of claims grounded — too many unverified statements |
| `moderate_grounding` | SOFT | 70–89% grounding — note in report |
| `empty_narrative` | HARD | LLM produced zero claims for a vendor — narrative is empty |
| `all_claims_ungrounded` | HARD | All claims failed grounding — LLM is hallucinating |
| `many_claims_removed` | SOFT | > 3 claims removed for a single vendor |

---

## What was wrong (and fixed in May 2026)

### 1. Custom facts completely missing from narrative context — HIGH
**Before:** `_build_fact_context()` iterated over certifications, insurance, SLAs, projects, and pricing — but skipped `extracted_facts` entirely. Any evaluation using custom targets (HR training records, ESG commitments, data residency statements, etc.) would produce a narrative with no mention of those facts at all. The LLM had no context to write about them.

**Fix:** `extracted_facts` is now included in `_build_fact_context()` with `Custom fact [target_id]: value` lines.

### 2. Source chunks truncated and mixed across vendors — MEDIUM
**Before:** `_format_chunks()` showed the LLM only the first 10 chunks from the combined `source_chunks` dict (all vendors together), each cut to 400 characters. For a 3-vendor evaluation with 10 chunks each, 20 of 30 chunks were invisible. For large chunks, facts beyond the 400-character mark disappeared. The LLM was forced to write grounded claims from a heavily truncated, mixed-vendor view.

**Fix:**
- In `run_explanation_agent`, source chunks are now filtered to vendor-specific chunks (`extraction.source_chunk_ids`) before being passed to the narrative generator.
- `_format_chunks()` now shows full chunk text with no character cap.
- Grounding verification also runs against vendor-specific chunks, preventing a claim about Vendor A from accidentally matching a chunk from Vendor B.

### 3. Zero claims reported as 100% grounding completeness — MEDIUM
**Before:** `grounding_completeness` defaulted to `1.0` when `total_claims == 0`. If the LLM returned no claims at all, the output appeared perfectly grounded. The Critic raised no flags, and the report would be published with empty vendor sections and no indication anything was wrong.

**Fix:** Default changed to `0.0`. Zero claims now triggers the existing HARD block at `< 0.70`. A `limitations` entry is also added per vendor with zero grounded claims.

### 4. System prompt was an inline Python string — LOW
**Before:** The full narrative generation system prompt was a multiline string hardcoded in `explanation.py`.

**Fix:** Moved to `app/prompts/explanation/generate_narrative.yaml`, registered in the prompt registry, pushed to LangSmith Hub.

### 5. Critic had no check for completely empty or fully-hallucinated narratives — MEDIUM
**Before:** The Critic checked overall `grounding_completeness` across all vendors combined, but did not detect when a single vendor's narrative had zero verifiable content. A vendor with 0 grounded claims and 5 removed claims would contribute to a lower overall percentage, but the specific problem (all claims for this vendor hallucinated) was invisible.

**Fix:** Two new HARD flags added to `critic_after_explanation`:
- `empty_narrative` — LLM returned zero claims for a vendor
- `all_claims_ungrounded` — LLM returned claims but every single one failed grounding
