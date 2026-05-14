# AI Governance & Responsible AI
*Version 1.0 — 2026-05-14*

---

## Governance Principles

This platform uses AI to assist — not replace — human decision-making in vendor evaluation. Every design decision reflects five principles:

1. **Grounded:** Every AI output is traceable to a verbatim source in the input document
2. **Fallible:** The system acknowledges when it lacks evidence (Critic hard-block) rather than hallucinating
3. **Auditable:** Every decision and every override has an immutable record
4. **Overrideable:** A human can always override any AI recommendation — but must justify it
5. **Transparent:** The report explains its reasoning in plain language, with citations

---

## AI Risk Classification

Following the EU AI Act (2024), this platform is classified as:

**High-Risk AI System** — Article 6(2), Annex III, Point 8:
> AI systems intended to be used by a contracting authority or utility, in the context of procurement decisions, that affect the fundamental rights of persons.

**Implications:**
- Mandatory human oversight for all procurement decisions (implemented via approval workflow)
- Technical documentation requirements (this document + architecture docs)
- Logging and traceability requirements (Critic audit trail, LangSmith, LangFuse)
- Post-market monitoring (LangFuse dashboard, rate monitor)

---

## Hallucination Prevention

### Defence-in-Depth Architecture

```
Layer 1: Retrieval Critic
  — Verifies chunks contain the specific facts the criterion asks for
  — LLM-based adequacy check before extraction begins
  — Confidence floor: 0.6 (configurable)

Layer 2: Extraction Critic
  — Verifies extracted fact correctly answers the criterion
  — Checks fact type matches criterion (PI ≠ PL, even if both are insurance)
  — Confidence floor: 0.7 (configurable)

Layer 3: Grounding Quote Check (Critic Agent)
  — Verbatim containment check: grounding_quote must appear in source text
  — Whitespace-normalised comparison (PDF table cell fix)
  — HARD block if grounding quote is empty or fails containment

Layer 4: Explanation Critic
  — Every claim in the final report must cite a source_chunk_id
  — HARD block if uncited claim detected

Layer 5: Human Override
  — Procurement Manager reviews extraction view
  — Can override any score with mandatory justification
  — All overrides create immutable audit records
```

### What Happens When Hallucination Is Detected

```
Critic issues HARD flag
  → Pipeline pauses at that agent
  → Procurement Manager notified via dashboard
  → Procurement Manager reviews: is the Critic correct?
    ├── Yes: Accept block, re-upload better document or adjust criteria
    └── No: Apply human override with justification → pipeline resumes
              Override logged in AuditOverride (immutable)
```

---

## Bias & Fairness

### Known Bias Risks

| Risk | Description | Mitigation |
|---|---|---|
| LLM training bias | Base LLM may score vendors from certain geographies lower due to training data skew | Rubric-based scoring (criteria + thresholds from config) limits free LLM judgment |
| Language bias | Non-English vendor responses may score lower if LLM struggles with translation nuances | Multilingual support planned; for now, English-only is disclosed |
| Format bias | PDF table parsing is imperfect — tabular data may not extract correctly | Whitespace normalisation fix; table-aware parsing (pdfplumber) in Tier 1 backlog |
| Historical bias in criteria | If criteria are written to favour incumbent vendors, AI faithfully applies the bias | Criteria are customer-configured — customers are responsible for fair criteria design |

### Audit for Bias

After any domain fine-tuning:
```bash
python tests/evaluation/bias_audit.py \
  --vendors tests/data/diverse_vendor_set.json \
  --criteria tests/data/standard_criteria.yaml
```

Expected: Score variance across vendor geography < 10% for equivalent evidence.

---

## Human-in-the-Loop Design

| Decision Type | AI Role | Human Role |
|---|---|---|
| Criterion relevance | AI retrieves and extracts | Human designs criteria (pre-run) |
| Fact extraction | AI extracts with grounding | Procurement Manager reviews extraction view |
| Scoring | AI scores with rubric | Department Head reviews scores |
| Recommendation | AI recommends with citations | Department Head approves or challenges |
| Final decision | AI provides recommendation | Human makes the binding decision |
| Override | AI flags deviation | Human justifies override in writing |

**The platform never makes a binding decision.** A human in the correct approval tier must approve every evaluation outcome. The AI accelerates the evaluation, not the decision.

---

## Data Governance

| Data Type | Governance |
|---|---|
| Vendor documents | Scoped to org + vendor, deleted on request, retained 7 years per procurement law |
| Extracted facts | Same scoping, linked to source chunk (lineage), immutable after extraction |
| Evaluation scores | Linked to facts, linked to decisions, retained 7 years |
| Audit overrides | Immutable, permanent (cannot be deleted even by admin) |
| LLM prompts + responses | LangSmith (OpenAI data policy) or local vLLM (no external logging) |

---

## ISO 42001 Alignment (AI Management System)

| ISO 42001 Clause | Our Implementation |
|---|---|
| 6.1 Risks and opportunities | Risk register in security_trust_model.md |
| 6.2 AI objectives | OKRs document |
| 8.4 AI system life cycle | This document + architecture docs |
| 8.5 Data for AI | Data requirements document |
| 9.1 Monitoring and measurement | Evaluation framework + observability plan |
| 10.1 Nonconformity and corrective action | Incident response plan |

**Status:** Gap assessment not yet completed. Target: Q4 2026.

---

## Responsible AI Checklist (Pre-Deployment)

Before deploying to any production customer:

- [ ] Critic agent hard-block rate < 2% on held-out test set
- [ ] Hallucination red team test: > 95% of injected hallucinations caught
- [ ] Cross-tenant isolation test: 500 requests, zero leakage
- [ ] Human override mechanism tested: override creates audit record, empty justification rejected
- [ ] 7-year retention verified: cleanup job does not delete within retention window
- [ ] Bias audit run on diverse vendor test set: variance < 10%
- [ ] Data residency confirmed for customer's region
- [ ] Customer informed this is a High-Risk AI System (EU AI Act Article 6)
- [ ] Customer has completed their own conformity assessment (Article 9) or is relying on ours
- [ ] Incident response contacts confirmed with customer
