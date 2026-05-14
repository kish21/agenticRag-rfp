# OKRs — Enterprise Vendor Governance Platform
*Version 1.0 — 2026-05-14 | Review cycle: Quarterly*

---

## How to Read This Document

Each Objective states what we are trying to achieve and why.
Each Key Result is a measurable outcome — not a task. 
Results are graded 0.0–1.0 at quarter-end. 0.7 is a good result; 1.0 means the target was too easy.

---

## Q2–Q3 2026 OKRs (Current)

---

### Objective 1 — Give the CEO real-time visibility into vendor spend across the organisation

**Why:** Today the CEO sees vendor spend only at quarter-end, via a manual CFO report. By then, duplicate contracts have been signed and pricing anomalies are already locked in. Real-time visibility prevents these mistakes before they happen.

| # | Key Result | Measurement | Target | Status |
|---|---|---|---|---|
| KR1.1 | CEO dashboard loads global RFP status (all departments, all regions) in under 3 seconds | p95 load time in production | 3s | Pending |
| KR1.2 | Duplicate vendor detection fires within 60 seconds of a second department opening an evaluation for the same vendor | Automated test: create 2 evals, same vendor, measure alert latency | 60s | Pending |
| KR1.3 | Cross-region pricing anomaly alert fires automatically when the same vendor's contract value differs >15% across regions | Automated test: register 2 contracts, same vendor, 20% price delta | 100% recall | Pending |
| KR1.4 | Total committed spend displayed on dashboard matches the sum of all signed contracts within ±1% | Reconciliation test against PostgreSQL sum | ±1% | Pending |

---

### Objective 2 — Make every vendor decision auditable and defensible

**Why:** Manual evaluations leave no evidence trail. Auditors, tribunals, and regulators increasingly require that AI-assisted decisions are fully documented. One failed audit costs more than the entire platform.

| # | Key Result | Measurement | Target | Status |
|---|---|---|---|---|
| KR2.1 | 100% of extracted facts have a non-empty grounding_quote that appears verbatim in the source document | Critic agent hard check — zero HARD blocks pass without grounding | 100% | Built |
| KR2.2 | Critic agent catches hallucinated claims in >95% of adversarial test cases | Red team test set: 50 deliberately hallucinated facts injected into evaluation runs | >95% | Pending |
| KR2.3 | 100% of human overrides create an AuditOverride record with non-empty justification | Integration test: attempt override with empty justification → expect 422 | 100% | Built |
| KR2.4 | Audit log is exportable as JSON for any evaluation run within 5 seconds | API test: GET /audit/{run_id}/export, measure response time | 5s | Pending |

---

### Objective 3 — Ship a production-ready multi-tenant platform for the first pilot customer

**Why:** The platform is complete in local dev (65/66 checkpoints). The gap is cloud deployment and the first real customer. The pilot validates that the design holds at production scale.

| # | Key Result | Measurement | Target | Status |
|---|---|---|---|---|
| KR3.1 | Zero cross-tenant data leakage across 500 simulated isolation tests (different org_ids, concurrent requests) | Automated: concurrent API calls across 10 simulated orgs, verify no cross-org data | Zero leaks | Pending |
| KR3.2 | End-to-end pipeline (3 vendors, 50-page PDFs each) completes in under 45 minutes on cloud infrastructure | Timed run on Modal + cloud Qdrant + cloud PostgreSQL | <45 min | Pending |
| KR3.3 | New tenant onboarded via admin API in under 30 minutes (no manual database steps) | Timed walkthrough: create org → add user → run first evaluation | <30 min | Pending |
| KR3.4 | Pipeline recovers from LLM rate limit (429) without human intervention in 99% of simulated cases | Load test: throttle LLM to 3 req/min, run 20 evaluations, measure auto-recovery | 99% | Built (rate_limiter.py) |

---

### Objective 4 — Eliminate per-token LLM cost for standard evaluation runs

**Why:** At scale, OpenAI API costs make per-evaluation pricing uneconomical. Modal vLLM (Qwen 2.5 72B) eliminates per-token cost and gives us a fine-tuning path for domain-specific models.

| # | Key Result | Measurement | Target | Status |
|---|---|---|---|---|
| KR4.1 | Modal vLLM deployment running and serving Qwen 2.5 72B responses via LLM_PROVIDER=modal | End-to-end evaluation with MODAL_LLM_ENDPOINT configured | Complete | Blocked (SSL/VPN) |
| KR4.2 | Evaluation output quality (Critic pass rate) on Modal vLLM is within 5% of OpenAI GPT-4o baseline | Run same 20 test evaluations on both providers, compare Critic pass rate | ≤5% delta | Pending |
| KR4.3 | Batch embedding on Modal A10G processes 200 chunks in under 5 seconds | Timed ingestion run with EMBEDDING_PROVIDER=modal | <5s | Pending |

---

## Q4 2026 OKRs (Planned)

| Objective | Key Results (draft) |
|---|---|
| O5: First paying customer live | KR: 1 customer signed, KR: 10 evaluations run in production, KR: NPS > 40 |
| O6: Domain fine-tuned model outperforms base model | KR: Procurement fine-tune reduces hallucination by 30%, KR: Model deployed on Modal, KR: A/B test run against GPT-4o |
| O7: ISO 27001 readiness | KR: Gap assessment complete, KR: 3 critical controls implemented, KR: External auditor engaged |

---

## OKR Grading Scale

| Score | Meaning |
|---|---|
| 0.0–0.3 | Failed — root cause review required |
| 0.4–0.6 | Partial — unblocked but incomplete |
| 0.7–0.9 | Good — expected delivery zone |
| 1.0 | Exceeded — target was too conservative |
