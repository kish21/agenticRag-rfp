# Prompt Registry
*Version 1.0 — 2026-05-14*

---

## Purpose

Every LLM prompt used by an agent is documented here. This document serves as:
- The single source of truth for what we ask the LLM to do
- A change log when prompts are revised
- The basis for prompt engineering experiments

Prompts stored in YAML (`platform.yaml`) are the authoritative versions. Prompts embedded in agent Python files are the runtime versions. When they differ, the Python file is authoritative (YAML is a reference copy until we build a prompt registry service).

---

## PR-01: Retrieval Critic Prompt

**Used by:** `app/core/retrieval_critic.py`
**Stored in:** `app/config/platform.yaml: retrieval_critic_prompt`
**Purpose:** LLM judges whether retrieved chunks contain sufficient evidence for the criterion.
**Temperature:** 0.0 (deterministic)
**Expected output:** `{"adequate": bool, "confidence": float, "missing": string}`

```
You are evaluating whether a set of retrieved document passages
contains evidence sufficient to judge a procurement criterion.

Criterion: {criterion_name}
Threshold rule (what passes): {what_passes}

Retrieved passages:
{chunks}

Do these passages collectively contain the specific facts the
threshold rule asks for (identifiers, dates, amounts, named
entities, certifications, etc.)? Be strict: if the rule asks for
a certificate NUMBER and the passages only describe the
certification in general, the answer is NO.

Return strict JSON only, no other text:
{
  "adequate": true,
  "confidence": 0.0,
  "missing": "what specific fact(s) are absent, if any (one short line)"
}
```

**Revision history:**
- v1.0 (2026-04-01): Initial
- v1.1 (2026-04-15): Added "identifiers, dates, amounts, named entities" to be strict — was producing false positives on vague passages

---

## PR-02: Extraction Critic Prompt

**Used by:** `app/core/extraction_critic.py`
**Stored in:** `app/config/platform.yaml: extraction_critic_prompt`
**Purpose:** LLM judges whether the extracted fact correctly answers the criterion based on the source passage.
**Temperature:** 0.0 (deterministic)
**Expected output:** `{"adequate": bool, "confidence": float, "missing": string, "should_retry": bool}`

```
You are verifying whether an extracted fact correctly answers a
procurement criterion, based on the source passage it was drawn from.

Criterion being evaluated: {criterion_name}
Criterion threshold rule: {what_passes}

The extraction agent extracted this fact:
  type: {fact_type}
  value: {fact_value}
  provider/issuer: {provider_or_issuer}
  amount/number/date: {key_identifier}

Source passage (the exact text the extractor read):
  {grounding_quote}

Question: Does the extracted fact correctly answer the criterion,
based on what the source passage actually states?

Be strict. Specifically:
  - If the criterion asks about Professional Indemnity but the
    extracted fact is Public Liability, the answer is NO.
  - If the criterion asks for a certificate number and the
    extracted fact has no certificate number, the answer is NO.
  - If the source passage mentions multiple related items, the
    extracted fact must match the SPECIFIC one the criterion asks
    about.

Return strict JSON only, no other text:
{
  "adequate": <true/false>,
  "confidence": <float 0.0-1.0>,
  "missing": "<what is absent or wrong — one short line>",
  "should_retry": <true if re-extracting could find the correct fact>
}
```

**Revision history:**
- v1.0 (2026-04-05): Initial
- v1.1 (2026-04-20): Added explicit PI vs PL example — was accepting wrong insurance type
- v1.2 (2026-05-01): Added `should_retry` field — enables targeted retry vs. accepting no-evidence verdict

---

## PR-03: HyDE Templates

**Used by:** `app/core/hyde.py`
**Stored in:** `app/config/platform.yaml: hyde_templates`
**Purpose:** Generate a hypothetical document of the appropriate type before embedding, improving retrieval recall.
**Temperature:** 0.3 (some variation acceptable)

### vendor_response template
```
Write a 2-3 sentence passage from a vendor response document
that would directly answer this requirement. Use formal business
language. Return only the passage, no preamble.

Requirement: {criterion}
```

### rfp_requirement template
```
Write a 1-2 sentence RFP clause that would contain the answer
to this question. Use formal procurement language. Return only
the passage, no preamble.

Question: {criterion}
```

### policy_document template
```
Write a 1-2 sentence policy statement that answers this question.
Use formal HR or legal policy language. Return only the passage,
no preamble.

Question: {criterion}
```

**Revision history:**
- v1.0 (2026-03-25): Initial — three templates for different document types

---

## PR-04: Query Rewriter Prompt

**Used by:** `app/core/query_rewriter.py`
**Purpose:** Rewrite an informal or ambiguous criterion into formal procurement language before embedding.
**Temperature:** 0.1

```
Rewrite the following procurement criterion as a formal, specific question
that a procurement analyst would ask when evaluating a vendor response.
Use precise, unambiguous language. Return only the rewritten question.

Original criterion: {criterion}
```

**Revision history:**
- v1.0 (2026-03-20): Initial

---

## PR-05: Extraction Prompt (Per Fact Type)

**Used by:** `app/agents/extraction.py`
**Purpose:** Extract a specific typed fact from the retrieved chunk text.
**Temperature:** 0.0 (deterministic extraction)
**Expected output:** JSON matching the fact type schema

### Certifications
```
Extract any ISO, Cyber Essentials, or other professional certifications
from the following text. Return a JSON object with:
  cert_type, cert_number, issuer, valid_until, grounding_quote

grounding_quote must be a verbatim excerpt from the text below that
contains the certification information. If no certification is present,
return null.

Text: {chunk_text}
```

### Insurance
```
Extract insurance policy information from the following text. Return a JSON object with:
  insurance_type, coverage_amount, currency, provider, policy_number, grounding_quote

insurance_type must be exactly: Professional_Indemnity, Public_Liability,
Employers_Liability, or Cyber_Insurance.

grounding_quote must be verbatim from the text. If no insurance is present, return null.

Text: {chunk_text}
```

### SLAs
```
Extract Service Level Agreement commitments from the following text. Return a JSON object with:
  sla_type, value, measurement_period, grounding_quote

grounding_quote must be verbatim from the text. If no SLA is present, return null.

Text: {chunk_text}
```

**Revision history:**
- v1.0 (2026-04-01): Initial
- v1.1 (2026-04-18): Added explicit insurance_type enum to prevent free-text insurance type extraction (was causing Evaluation scoring failures)

---

## PR-06: Evaluation Scoring Prompt

**Used by:** `app/agents/evaluation.py`
**Purpose:** Score a vendor against one criterion using extracted PostgreSQL facts.
**Temperature:** 0.1

```
You are a senior procurement analyst scoring a vendor against a specific criterion.

Criterion: {criterion_name}
Threshold rule (what passes): {what_passes}
Weight: {weight}

Evidence (extracted facts from vendor documents):
{facts_json}

Score this vendor on this criterion from 0–100.
- 85–100: Criterion clearly met, strong evidence
- 70–84: Criterion likely met, adequate evidence
- 50–69: Criterion partially met, some gaps
- 0–49: Criterion not met or insufficient evidence

Return JSON only:
{
  "score": <int 0-100>,
  "confidence": <float 0.0-1.0>,
  "rationale": "<one sentence — cite the specific fact that drove the score>",
  "evidence_citations": [<list of source_chunk_ids>]
}
```

**Revision history:**
- v1.0 (2026-04-08): Initial
- v1.1 (2026-04-25): Added explicit score band definitions to calibrate scoring — was seeing over-generous scores

---

## Prompt Change Policy

1. Any prompt change must be logged here with the version, date, and reason
2. Regression test (extraction_eval.py) must be re-run after any extraction prompt change
3. Provider parity test must be re-run after any prompt change (some prompts behave differently on Anthropic vs. OpenAI)
4. Temperature must not be raised above 0.1 for extraction/critic prompts without documented justification
