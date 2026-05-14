# Business Case — Enterprise Vendor Governance & Spend Intelligence Platform
*Version 1.0 — 2026-05-14*

---

## Executive Summary

Large enterprises conduct hundreds of RFP evaluations per year across multiple departments and geographies. Each evaluation is siloed: the IT department in Singapore, HR in Germany, and Marketing in the US may all be evaluating the same vendor simultaneously — at different prices, with no shared intelligence.

This platform centralises vendor evaluation into an AI-driven pipeline and surfaces the aggregate picture to the CEO and CFO in real time: what RFPs are active, who was chosen, what the company is committing to pay, and where it is overpaying.

---

## The Problem

### Cost of the Status Quo

| Problem | Estimated Cost |
|---|---|
| Analyst time per RFP evaluation | 6–10 hours per vendor |
| Average vendors per RFP | 3–5 |
| RFPs per year (mid-size enterprise) | 50–200 |
| Total analyst hours per year | 900 – 10,000 hours |
| Duplicate vendor onboarding (same vendor, 3 regions) | 3× onboarding cost |
| Pricing inconsistency across regions | 10–25% overpay identified in audits |
| Human error in compliance scoring | 1 in 5 evaluations has a scoring error |

### What the CEO Cannot See Today

- Total active RFPs across the organisation at any point in time
- Whether two departments are evaluating the same vendor simultaneously
- Whether the company is paying different prices to the same vendor in different regions
- Whether every vendor decision has a documented, auditable evidence trail
- Which departments are overdue on their renewal evaluations

---

## The Solution

An agentic AI platform that:

1. **Automates RFP evaluation** — 9-agent pipeline ingests vendor documents, extracts structured facts, scores against criteria, and produces a cited recommendation in under 45 minutes
2. **Consolidates across departments and regions** — all evaluations flow into a single data model, enabling cross-department and cross-region views
3. **Surfaces executive intelligence** — CEO dashboard shows real-time spend commitment, vendor concentration risk, duplicate evaluations, and pricing anomalies
4. **Creates a permanent audit trail** — every decision is grounded in a verbatim quote from source documents, every override is recorded, all data is retained for 7 years

---

## Financial Case

### Assumptions (mid-size enterprise, 100 RFPs/year)

| Item | Estimate |
|---|---|
| Analyst time saved per RFP | 20 hours (from 28h to 8h) |
| Average analyst cost | £75/hour |
| Savings per RFP | £1,500 |
| Annual savings (100 RFPs) | £150,000 |
| Overpay reduction (10% of £5M vendor spend) | £500,000 |
| Duplicate vendor onboarding reduction | £50,000 |
| **Total year-1 benefit** | **£700,000** |

### Platform Cost

| Item | Cost |
|---|---|
| Modal GPU compute (A100, burst) | ~£2,000/month |
| LangSmith observability | £500/month |
| Infrastructure (Qdrant + PostgreSQL, cloud) | £300/month |
| **Total annual platform cost** | **~£33,600** |

### ROI

**Year-1 net benefit: ~£666,000**
**Payback period: < 1 month after deployment**

---

## Strategic Value Beyond Year 1

- **Fine-tuned domain models** — procurement, HR, legal, IT domain-specific LLMs trained on company RFP data reduce hallucination to near zero
- **Vendor market intelligence** — aggregate pricing database across all customers creates a benchmarking advantage (anonymised)
- **Compliance automation** — ISO 42001 / SOC 2 audit readiness built into every evaluation run
- **Multi-language support** — evaluations in 12 languages, enabling APAC and LATAM expansion without additional headcount

---

## Risk of Not Acting

- Regulatory exposure: manual RFP evaluations with no audit trail fail GDPR Article 22 (automated decision making) and procurement law in public sector
- Competitive disadvantage: peers using AI evaluation cut procurement cycles from weeks to hours
- Talent cost: hiring additional procurement analysts to handle RFP volume growth is £60–90K per head

---

## Decision Requested

Approve build and deployment of the Enterprise Vendor Governance Platform.
First deployment target: one enterprise customer pilot, Q3 2026.
