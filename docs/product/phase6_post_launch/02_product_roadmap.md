# Product Roadmap — v2 and Beyond
*Version 1.0 — 2026-05-14*

---

## Now (Q2 2026) — Complete & Production-Ready

- 9-agent pipeline: Planner, Ingestion, Retrieval, Extraction, Evaluation, Comparator, Decision, Explanation, Critic
- CEO dashboard: global spend visibility, duplicate vendor alerts, pricing anomaly detection
- Multi-tenant: org_id isolation, RBAC, RLS
- Multi-provider: 6 LLM providers, 4 embedding providers, 4 rerankers
- Human override with audit trail
- 65/66 checkpoints passed

---

## Next (Q3 2026) — Pilot Customer

### Infrastructure
- [ ] Cloud PostgreSQL (unblocks Modal scheduled jobs, pilot customer data)
- [ ] Cloud Qdrant (production scale, 10M+ vectors)
- [ ] Modal deploy (unblock SSL/VPN issue — deploy Qwen 2.5 72B on A100)
- [ ] Compute provider abstraction (`compute_provider.py`) — Azure Functions, AWS Lambda, local_worker

### Agent Improvements (Tier 1 from backlog)
- [ ] Table-aware PDF parsing (`pdfplumber` / `pymupdf4llm`) — biggest source of extraction failures
- [ ] Extraction via `tool_use` / function-calling — eliminate JSON parsing fragility
- [ ] Configurable approval tiers per org (move £100K/£500K to `org_settings`) — currently hardcoded
- [ ] Citation footnotes with page numbers in PDF report

### Customer Delivery
- [ ] Vendor submission portal (vendors upload directly, without email)
- [ ] Onboarding flow: self-service tenant setup in < 30 minutes
- [ ] User manual (Procurement Manager, Department Head, IT Admin)

---

## Q4 2026 — Scale & Differentiation

### Domain Fine-Tuning
- [ ] Procurement domain fine-tune (Qwen 2.5 72B, Modal H100)
  - Training data: RFP/vendor response pairs with annotated fact extractions
  - Expected: 30% reduction in hallucination rate vs. base model
- [ ] HR domain fine-tune (HR policy question-answer pairs)
- [ ] Legal domain fine-tune (contract clause pairs)

### Advanced Retrieval
- [ ] Query decomposition for multi-part criteria (e.g., "ISO 27001 AND Cyber Essentials AND SOC 2")
- [ ] Adaptive-K selection based on rerank score spread (fewer chunks when top-1 is clearly dominant)
- [ ] RAPTOR recursive retrieval for complex, hierarchical RFP documents

### Advanced Evaluation
- [ ] Bayesian confidence intervals on evaluation scores
- [ ] Monte Carlo rank stability simulation in Comparator
- [ ] Comparative rubric scoring (cross-vendor normalisation)
- [ ] Critic flag learning from human overrides (online adaptation)

### Platform
- [ ] Multilingual report output (12 languages — EN, FR, DE, ES, PT, ZH, JA, KO, AR, NL, IT, PL)
- [ ] SOC 2 Type I readiness assessment
- [ ] ISO 27001 gap assessment
- [ ] ISO 42001 (AI Management System) gap assessment

---

## 2027 — Market Expansion

### Vendor Market Intelligence
- Anonymised aggregate pricing database across all customer evaluations
- Benchmark pricing: "your region is paying 23% above the anonymised market median for this category"
- Vendor concentration risk scoring across the customer's entire portfolio

### Conflict of Interest Detection
- ERP / HR integration: detect if approving procurement manager has financial relationship with vendor
- Requires HR and ERP API integration (Workday, SAP HR)

### Contract Lifecycle Integration
- After vendor decision: auto-generate contract template with extracted SLAs, pricing, terms pre-filled
- Integration with Ironclad or Icertis for contract management post-decision
- This is the downstream phase we explicitly excluded from v1 — now becomes the v3 feature

### Compliance Certifications
- SOC 2 Type II
- ISO 27001 certified
- ISO 42001 certified (AI Management System)
- NHS DSPT (Data Security and Protection Toolkit)
- UK G-Cloud listing (public sector procurement framework)

### Vertical Specialisations
- NHS / UK Public Sector: Pre-loaded NHS Supply Chain criteria templates, DSPT compliance checks
- Financial Services: FCA supply chain risk criteria, DORA compliance requirements
- Construction / Infrastructure: PAS 91 pre-qualification questionnaire automation

---

## What We Will Not Build

| Feature | Reason |
|---|---|
| Contract management (post-decision) | Icertis/Ironclad domain — complement them, don't compete |
| Invoice processing / payments | Coupa/Ariba domain |
| Vendor negotiation automation | Requires real-time negotiation AI — different product entirely |
| Fully autonomous decisions (no human approval) | Contradicts our governance principle; EU AI Act requires human oversight for high-risk AI |
| Generic document Q&A | Too broad — we maintain procurement-domain focus |

---

## Roadmap Summary

```
Q2 2026 ─ Platform complete, 65/66 checkpoints
Q3 2026 ─ First pilot customer live (cloud infra + Tier 1 agent improvements)
Q4 2026 ─ Domain fine-tune launched + multilingual + SOC 2 assessment
Q1 2027 ─ 10 paying customers, vendor intelligence beta
Q2 2027 ─ ISO certifications, G-Cloud listing, NHS vertical
2027+   ─ Contract lifecycle integration, conflict-of-interest detection
```
