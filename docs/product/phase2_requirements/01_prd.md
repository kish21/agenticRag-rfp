# Product Requirements Document (PRD)
*Version 1.0 — 2026-05-14*

---

## 1. Overview

**Product:** Enterprise Vendor Governance & Spend Intelligence Platform
**Primary surface:** CEO / Executive dashboard (cross-department, cross-region)
**Underlying engine:** 9-agent AI pipeline for RFP document evaluation
**Target customers:** Mid-to-large enterprises, NHS Trusts, local councils, FTSE 250 companies

---

## 2. Problem Statement

Enterprise organisations conduct RFP evaluations in silos. Different departments in different countries evaluate vendors independently, with no shared intelligence. The CEO has no real-time visibility into what vendor commitments are being made across the organisation. Pricing inconsistencies, duplicate vendor evaluations, and undocumented override decisions cost enterprises millions annually and create regulatory exposure.

---

## 3. Goals

### Must Have (P0)
- Automated vendor document ingestion and evaluation via 9-agent AI pipeline
- Structured fact extraction with verbatim grounding quotes — every fact traceable to source
- Critic agent that hard-blocks the pipeline if hallucination is detected
- CEO dashboard: active RFPs, committed spend, vendor choice, cross-department view
- Multi-tenant data isolation: org_id + vendor_id scoping, zero cross-tenant leakage
- Human override with mandatory justification, immutable audit record
- Role-based access control: CEO sees all, Department Head sees their scope

### Should Have (P1)
- Duplicate vendor detection: same vendor active in 2+ departments simultaneously → alert
- Pricing anomaly detection: same vendor, different price across regions → alert
- Vendor concentration risk: single vendor >30% of department spend → flag
- Multi-LLM provider support: OpenAI, Anthropic, Azure, local, Modal — config-only switch
- PDF report with citations generated automatically at end of each evaluation
- Approval workflow: pipeline routes to correct approver tier based on contract value

### Nice to Have (P2)
- Fine-tuned domain LLMs: procurement, HR, legal, IT
- Multilingual evaluations (12 languages)
- Vendor submission portal
- External auditor read-only access
- SOC 2 / ISO 27001 / ISO 42001 certification

---

## 4. Non-Goals

- This platform does not manage contracts after vendor selection (that is Icertis/Ironclad territory)
- This platform does not process invoices or payments (that is Coupa/Ariba territory)
- This platform does not negotiate with vendors on behalf of the customer
- This platform does not replace the human decision maker — it informs and documents the decision

---

## 5. Success Metrics

| Metric | Baseline | Target |
|---|---|---|
| Evaluation time per RFP (3 vendors) | 20–28 hours | < 45 minutes |
| Extraction accuracy (facts with correct grounding) | N/A (manual) | > 95% |
| Hallucination rate (Critic-blocked runs per 100) | N/A | < 2 per 100 |
| CEO dashboard data freshness | Weeks (quarterly report) | Real-time (< 30 seconds) |
| Duplicate vendor alerts fired correctly | 0% (no system) | > 90% recall |
| Cross-region pricing anomalies detected | 0% (no system) | 100% of registered cases |
| Override audit trail completeness | < 10% (email only) | 100% (enforced by system) |
| Time to onboard new tenant | Days (manual) | < 30 minutes (self-service) |

---

## 6. User Stories

### CEO
- As a CEO, I want to see all active RFPs across all departments and regions on one dashboard, so I can monitor vendor commitment without asking each department head.
- As a CEO, I want to be alerted immediately when two departments are evaluating the same vendor simultaneously, so I can trigger a consolidated negotiation.
- As a CEO, I want a weekly digest of all vendor decisions made that week, so I can stay informed without logging in daily.

### Procurement Manager
- As a Procurement Manager, I want to upload multiple vendor PDFs and trigger an evaluation in one action, so I do not have to manage a multi-step process.
- As a Procurement Manager, I want to see every extracted fact alongside the verbatim text from the source document, so I can verify the AI's reading.
- As a Procurement Manager, I want to override a score or decision with a mandatory justification, so my professional judgement is recorded and auditable.

### Department Head
- As a Department Head, I want a one-page summary of the evaluation result — recommended vendor, score, key reasons — so I can make an approval decision in under 15 minutes.
- As a Department Head, I want to approve or challenge a recommendation from my dashboard with a single action, so I do not need a separate email chain.

### CFO
- As a CFO, I want to see total committed vendor spend by region and category in real time, so I can produce an accurate board report without manual aggregation.
- As a CFO, I want to be notified before any contract above £500K is signed, so I can review and approve or block it.

### IT Admin
- As an IT Admin, I want to onboard a new department as a tenant without touching source code, so I can self-serve without raising vendor tickets.
- As an IT Admin, I want to configure the LLM provider to use our Azure OpenAI deployment, so vendor data never leaves our Azure tenancy.

---

## 7. Constraints

- All vendor document data scoped by org_id — no cross-tenant reads
- All LLM calls go through `call_llm()` — no direct provider SDK calls in agent files
- Critic Agent cannot be bypassed — hard blocks must escalate to a human
- All overrides create an AuditOverride record — no direct database edits
- 7-year audit retention is enforced in product.yaml — not configurable below 7 years
- No hardcoded business logic in agent files — all thresholds read from config

---

## 8. Open Questions

| Question | Owner | Due |
|---|---|---|
| What is the minimum data set to train a procurement-domain fine-tuned model? | AI Engineering | Q4 2026 |
| Which compliance frameworks to certify first: SOC 2 or ISO 27001? | Legal | Q3 2026 |
| What is the right pricing model: per-evaluation, per-seat, or per-RFP-volume tier? | Product | Q3 2026 |
| How should the vendor submission portal authenticate vendors? | Engineering | Q4 2026 |

---

## 9. Dependencies

| Dependency | Status |
|---|---|
| Qdrant cloud (production) | Pending — currently local Docker |
| PostgreSQL cloud (production) | Pending — currently local Docker |
| Modal deployment (GPU inference) | Pending SSL / VPN issue |
| LangSmith production workspace | Active |
| LangFuse cloud | Active |
