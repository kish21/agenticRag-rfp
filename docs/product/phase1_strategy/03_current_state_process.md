# Current State Process Map — RFP Evaluation (Before Platform)
*Version 1.0 — 2026-05-14*

---

## The "Before" Picture

This document maps how RFP evaluations are conducted today across enterprise departments — the manual, siloed, error-prone baseline the platform replaces.

---

## Current Process: Department-Level RFP Evaluation

### Step-by-Step Flow

```
1. RFP ISSUED
   Department head identifies need → drafts RFP document manually (Word/Google Docs)
   Sends to 3–5 shortlisted vendors via email
   ↓ (1–2 weeks waiting for responses)

2. VENDOR RESPONSES RECEIVED
   Responses arrive as PDF/Word attachments via email
   Procurement analyst saves to a shared drive folder (no version control)
   ↓

3. MANUAL READING
   Analyst reads each vendor response — typically 50–200 pages per vendor
   Highlights relevant sections manually
   Time: 4–6 hours per vendor
   ↓

4. SPREADSHEET SCORING
   Analyst creates an Excel scoring matrix
   Scores criteria manually based on reading
   No grounding: score is opinion, not a verbatim extract
   Time: 2–4 hours
   ↓

5. INTERNAL REVIEW MEETING
   Procurement Manager and Department Head review the spreadsheet
   Disagreements resolved by seniority, not evidence
   Time: 1–3 hours
   ↓

6. LEGAL REVIEW (sometimes skipped)
   Legal team manually checks contract clauses in the preferred vendor's response
   Separate document, separate email chain
   Time: 2–4 hours
   ↓

7. APPROVAL
   Email chain to Department Head → Regional Director → CFO (depending on spend)
   No formal approval system — approval is an email reply
   Time: 1–5 days
   ↓

8. VENDOR NOTIFICATION
   Procurement Manager emails the winning vendor
   Losing vendors may or may not be notified
   No documented rationale shared externally
   ↓

9. CONTRACT SIGNED
   Legal drafts or reviews contract separately
   No link between the evaluation and the contract in any system
```

---

## Pain Points Identified

### Speed
- **Total elapsed time: 2–6 weeks** per evaluation (including waiting)
- **Active analyst effort: 8–15 hours** per evaluation (3–5 vendors)
- Bottleneck: manual reading and scoring dominates

### Quality
- Scores are opinion-based — no verbatim evidence trail
- Different analysts score the same criterion differently (no rubric calibration)
- Legal clauses are missed when legal review is skipped (common under deadline pressure)
- Hallucination equivalent: analysts misremember or misread details from long documents

### Visibility
- **The CEO has zero real-time visibility** into what RFPs are active
- No system knows that IT in Singapore and HR in Germany are evaluating Vendor X simultaneously
- No one knows the company is paying Vendor X $200K in APAC and €280K in EMEA for the same service
- Vendor spend is only visible at year-end during the CFO's manual audit

### Governance
- Approval is an email — no immutable record
- Overrides (changing a recommendation) are informal — no audit trail
- 7-year retention is a shared drive folder — no enforced policy
- GDPR compliance for vendor data is ad-hoc

### Duplication
- Every department builds its own scoring spreadsheet from scratch
- Vendor onboarding (legal, finance vetting) is repeated per department
- No shared vendor knowledge base — the same compliance check is done 5 times for the same vendor

---

## Current State Metrics (Baseline)

| Metric | Current State |
|---|---|
| Average evaluation time per vendor | 6–8 hours (analyst) |
| Average evaluation time per RFP (3 vendors) | 20–28 hours |
| Scoring error rate | ~20% (missing or misread clauses) |
| CEO visibility into active RFPs | 0% (no dashboard exists) |
| Duplicate vendor evaluations detected | 0% (no cross-dept view) |
| Cross-region pricing anomalies detected | 0% (no aggregation) |
| Evaluations with documented override rationale | <10% |
| Evaluations with verbatim evidence trail | <5% |

---

## The "After" Picture (Platform Target State)

| Metric | Target State |
|---|---|
| Average evaluation time per vendor | < 5 minutes (agent pipeline) |
| Average evaluation time per RFP (3 vendors) | < 45 minutes total |
| Scoring error rate | < 5% (Critic agent + grounding quotes) |
| CEO visibility into active RFPs | 100% real-time dashboard |
| Duplicate vendor evaluations detected | > 90% via cross-dept vendor index |
| Cross-region pricing anomalies detected | 100% (automated on contract save) |
| Evaluations with documented override rationale | 100% (enforced by system) |
| Evaluations with verbatim evidence trail | 100% (enforced by Critic agent) |

---

## Process Map: After Platform

```
1. UPLOAD
   Procurement Manager uploads vendor PDFs via web UI (drag + drop)
   Platform confirms RFP identity before proceeding (prevents wrong-document errors)
   ↓ < 1 minute

2. INGESTION AGENT
   Chunks documents, creates dense + sparse embeddings, indexes in Qdrant
   ↓ < 3 minutes per vendor

3. EXTRACTION AGENT
   Extracts structured facts (certifications, SLAs, insurance, pricing, projects)
   Every fact grounded to a verbatim quote from the source document
   Stores in PostgreSQL
   ↓ < 2 minutes

4. EVALUATION AGENT
   Scores each criterion against extracted PostgreSQL facts (NOT raw text)
   Reads rubric from config — no hardcoded scoring logic
   ↓ < 2 minutes

5. COMPARATOR AGENT
   Cross-vendor ranking with rank stability check
   Identifies differentiators between vendors
   ↓ < 1 minute

6. CRITIC AGENT (runs after every agent)
   Validates grounding, scores, citations at each step
   Hard block if hallucination detected — escalates to Procurement Manager
   ↓ continuous

7. DECISION AGENT
   Routes to approval tier based on contract value
   Under $100K → Department Head
   $100K–$500K → Regional Director
   $500K–$1M → CFO
   Over $1M → Board
   ↓ < 30 seconds

8. EXPLANATION AGENT
   Generates PDF report — every claim cited to a verbatim source quote
   Report available to all stakeholders via dashboard
   ↓ < 2 minutes

9. CEO DASHBOARD UPDATES
   RFP marked complete, vendor choice recorded, spend committed
   Duplicate vendor alert fires if same vendor active in another department
   Pricing anomaly alert fires if spend differs >15% from regional benchmark
   ↓ real-time
```
