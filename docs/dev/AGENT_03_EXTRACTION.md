# Agent 03 — Extraction Agent

## What it does (plain English)

After the Retrieval Agent finds the most relevant text passages from a vendor's document, the Extraction Agent reads those passages and pulls out specific facts — like "what certifications does this vendor hold?" or "what are their response time guarantees?" — and saves those facts to the database in a structured, searchable format.

Think of it as a specialist reader who goes through highlighted paragraphs and fills in a structured form, so the Evaluation Agent doesn't have to re-read the original document — it just reads the form.

---

## Step-by-step process

```
1. Filter out boilerplate chunks (legal disclaimers, T&Cs — not vendor claims)
2. Build context string — each chunk labelled with [chunk_id] [section_type]
3. Ask LLM to extract facts — JSON schema is built from the customer's evaluation criteria
4. Parse the JSON response into typed Pydantic objects
5. Retry loop — if a mandatory fact was missed, ask the LLM again more specifically
6. Score completeness (how many required fact types were found)
7. Score hallucination risk (does each grounding_quote appear verbatim in source?)
8. Critic check — verifies every quote programmatically (no LLM)
9. Save to PostgreSQL — only if Critic does not block
```

---

## Key design rules

| Rule | Why |
|------|-----|
| Every extracted fact has a `grounding_quote` | Verbatim sentence from the source — auditable, no hallucination |
| Only extracts what the customer asked for | Schema is built from `EvaluationSetup.extraction_targets` — not hardcoded |
| Saves to PostgreSQL, not Qdrant | Structured facts for the Evaluation Agent to score — Qdrant is raw text only |
| Critic must approve before save | Grounding quotes are checked programmatically — blocked facts are never persisted |
| Boilerplate excluded | Legal disclaimers contain no vendor commitments — sending them confuses the LLM |

---

## Fact types

The extraction schema is **100% driven by the customer's evaluation criteria**. Whatever `extraction_targets` are set up at the start of an evaluation run, those are the only sections the LLM is asked to fill in.

Standard types (only included if the evaluation asks for them):

| Type | Example |
|------|---------|
| `certification` | "ISO 27001 certified, certificate number XYZ, expiry Dec 2026" |
| `insurance` | "£10M professional indemnity, renewed annually" |
| `sla` | "99.9% uptime SLA, 4-hour critical response time" |
| `project` | "Deployed for NHS Scotland, 50k users, 2023–present" |
| `pricing` | "£120/user/month, annual billing, 10% discount for 3-year term" |
| `custom` | Anything the customer defines — e.g. "ESG commitments", "UK data residency" |

---

## Retry loop

If the first extraction attempt misses a **mandatory** fact (one that the Critic flags as required), the retry loop:
1. Tells the LLM exactly what criterion failed
2. Shows what the previous attempt returned (or that it returned nothing)
3. Asks it to search more carefully for that specific fact
4. Tries up to 3 times per fact type

The retry prompt is in `app/prompts/extraction/retry_extract.yaml` and managed in LangSmith Hub.

---

## Files

| File | Role |
|------|------|
| `app/agents/extraction.py` | Main pipeline — orchestrates all steps |
| `app/agents/_extraction/prompts.py` | Builds dynamic JSON schema from extraction targets |
| `app/agents/_extraction/parsing.py` | Converts LLM JSON → typed Pydantic objects |
| `app/agents/_extraction/scoring.py` | Completeness and hallucination risk scores |
| `app/agents/_extraction/retry_loop.py` | Targeted retry for missed mandatory facts |
| `app/prompts/extraction/extract_facts.yaml` | Main extraction prompt (variable: `{schema}`) |
| `app/prompts/extraction/retry_extract.yaml` | Retry prompt (7 variables) |
| `app/db/fact_store.py` | Saves to PostgreSQL |

---

## What was wrong (and fixed in May 2026)

### 1. Hardcoded fact types — CRITICAL
**Before:** The extraction schema always asked the LLM to find certifications, insurance, SLAs, projects, and pricing — regardless of what the customer actually needed. An HR evaluation looking for "training records" and "DEI policies" would get back empty certification/insurance/SLA arrays and miss the actual custom targets entirely.

**Fix:** `_schema_description()` in `prompts.py` now builds the JSON schema purely from `EvaluationSetup.extraction_targets`. If an evaluation has no certification target, the schema has no certification section.

### 2. Completeness score always wrong — CRITICAL
**Before:** Completeness was calculated as `found / 6` (always divided by 5 standard types + custom), so an HR evaluation that found all 4 of its custom facts would score 4/6 = 67% — appearing to have missed something, when it hadn't.

**Fix:** `_extraction_completeness()` in `scoring.py` now only counts fact types that have entries in `extraction_targets`. Score is `found / (number of target types)`.

### 3. Boilerplate polluting context — MEDIUM
**Before:** Legal disclaimer chunks (section_type = "boilerplate") were sent to the LLM alongside real vendor claims. These contain language like "nothing in this document constitutes a warranty" which can confuse grounding checks.

**Fix:** Boilerplate chunks are filtered out before building context. Falls back to all chunks only if filtering removes everything.

### 4. LLM couldn't distinguish chunk relevance — MEDIUM
**Before:** All chunks in context looked identical — no indication of whether a chunk was a direct answer to an RFP question or just background text.

**Fix:** Context now shows `[chunk_id] [section_type]` headers so the LLM can prioritise `requirement_response` chunks over `background` ones.

### 5. Prompts hardcoded in Python — LOW
**Before:** Extraction and retry prompts were inline strings in Python files — not versionable, not updateable without code deployment.

**Fix:** Both prompts moved to `app/prompts/extraction/` YAML files, registered in the prompt registry, and pushed to LangSmith Hub for live editing.
