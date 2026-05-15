# Competitive Analysis
*Version 1.0 — 2026-05-14*

---

## Market Landscape

The vendor evaluation and procurement automation space has several incumbents, but none address the specific combination of: AI-native multi-agent evaluation + CEO-level cross-department spend intelligence + full audit trail with verbatim grounding.

---

## Competitor Matrix

| Capability | **This Platform** | Icertis | Ironclad | Coupa | Ariba (SAP) | ChatGPT/Claude (raw) |
|---|---|---|---|---|---|---|
| AI-native document evaluation | Yes — 9-agent pipeline | Partial (contract AI only) | Partial (contract AI only) | No | Limited | Yes but no structure |
| Multi-department CEO dashboard | Yes — core feature | No | No | Partial | Partial (expensive) | No |
| Cross-region pricing anomaly detection | Yes — automated alerts | No | No | Partial | No | No |
| Verbatim grounding quotes per fact | Yes — enforced by Critic | No | No | No | No | No |
| Critic agent / hallucination guardrails | Yes — hard block | No | No | No | No | No |
| Multi-LLM provider (Azure, OpenAI, local) | Yes — config only | No | No | No | No | N/A |
| Air-gapped / on-prem deployment | Yes — local_worker mode | No | No | No | Limited | No |
| Human override with audit trail | Yes — enforced | No | Manual | Partial | Partial | No |
| 7-year retention by design | Yes — product.yaml config | Yes | Yes | Yes | Yes | No |
| Open source stack | Mostly — Qdrant, Postgres, BGE | No | No | No | No | No |
| Per-evaluation cost | Modal GPU burst only | Per-seat enterprise | Per-seat enterprise | Per-seat enterprise | Per-seat enterprise | Per-token |
| Setup complexity | .env file | 6–18 month implementation | 3–12 month implementation | 6+ months | 12–24 months | Minutes |

---

## Competitor Deep-Dives

### Icertis (Contract Lifecycle Management)
- **Focus:** Contract management after vendor selection — not the evaluation phase
- **AI:** Contract clause extraction, obligation tracking
- **Gap:** Does not evaluate competing vendor proposals. No CEO spend dashboard. No multi-agent pipeline. Costs $200K–$2M/year for enterprise.
- **Our advantage:** We cover the evaluation phase (before contract) that Icertis ignores. We are the missing layer upstream.

### Ironclad
- **Focus:** Contract review and approval workflows for legal teams
- **AI:** Contract redlining, clause risk flagging
- **Gap:** Single-vendor contract review, not multi-vendor comparison. No cross-department visibility. Legal-team-centric, not CEO-centric.
- **Our advantage:** Multi-vendor simultaneous evaluation, executive dashboard, procurement-domain scoring rubrics.

### Coupa (Business Spend Management)
- **Focus:** Spend visibility and procurement workflows — closest to our executive dashboard
- **AI:** Limited — mostly rules-based automation
- **Gap:** No AI-native document evaluation. No agent pipeline. No verbatim grounding. Complex, expensive implementation (6+ months).
- **Our advantage:** AI-native evaluation with grounded evidence. Faster time to value (days, not months).

### SAP Ariba
- **Focus:** Full procure-to-pay suite for very large enterprises
- **AI:** Basic NLP for supplier matching
- **Gap:** Heavyweight, designed for Fortune 500. Evaluation is still largely manual within Ariba. $500K+ implementation cost.
- **Our advantage:** Purpose-built for the evaluation phase, deploying in a day, 1/10th the cost.

### Raw LLM (ChatGPT/Claude via API)
- **What people do today:** Upload a PDF and ask "which vendor is better?"
- **Gap:** No structure, no grounding, no audit trail, no hallucination detection, no cross-vendor comparison framework, no CEO dashboard, no multi-tenancy.
- **Our advantage:** We wrap the LLM capability in the enterprise guardrails (Critic agent, PostgreSQL facts, grounding quotes, RBAC, audit trail) that make it usable in a regulated environment.

---

## Our Differentiated Position

### The Three Things No Competitor Has Together

1. **Grounded AI evaluation with hard guardrails**
   Every extracted fact has a verbatim quote. The Critic agent blocks the pipeline if hallucination is detected. No competitor enforces this at the system level.

2. **CEO-level cross-department spend intelligence**
   Real-time view of active RFPs, committed spend, duplicate vendor alerts, pricing anomalies across all departments and regions. Coupa gets closest but without AI evaluation underneath.

3. **Configurable for any enterprise stack**
   One .env file switches between OpenAI, Azure OpenAI, Anthropic, local models, air-gapped deployment. No code changes. No other evaluation platform offers this.

---

## Market Positioning Statement

> For enterprise organisations that conduct RFP evaluations across multiple departments and geographies, this platform is the only AI-native vendor evaluation system that combines agent-driven document analysis with CEO-level spend intelligence and a full, enforced audit trail — deployable in hours, not months.

---

## Pricing Positioning

| Segment | Existing tools cost | Our target price | Advantage |
|---|---|---|---|
| Mid-market (50–200 RFPs/year) | $80K–$200K/year (Coupa/Icertis) | $30K–$60K/year | 50–70% lower |
| Enterprise (200+ RFPs/year) | $200K–$2M/year (SAP Ariba) | $60K–$150K/year | 70–80% lower |
| Public sector | Manual (no tooling budget) | $20K–$40K/year | Greenfield |
