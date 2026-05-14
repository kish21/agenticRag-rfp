# Project Evaluation — Technical & Product Assessment
*Version 1.0 — 2026-05-14*

---

## What This Document Is

A structured technical and product assessment of the Enterprise Vendor Governance Platform.

Useful for:
- Identifying next high-value improvements
- Demonstrating technical maturity (the ability to critique your own work)

---

## 1. Architecture Quality

### What is strong

**Multi-agent pipeline with enforced Critic topology**
The 9-agent LangGraph graph is wired so the Critic node receives edges from every other agent. This is enforced at graph compilation time — you cannot add an agent without connecting it to the Critic. This is a production-quality design choice, not an academic one.

**Two storage layers with clear rationale**
The Qdrant (vector) + PostgreSQL (structured facts) separation is correctly motivated: evaluation requires SQL joins and typed comparisons, which Qdrant cannot provide. The `source_chunk_id` link preserves full lineage from decision back to source document. This is the kind of design decision that separates engineers who have built real systems from those who have only done tutorials.

**Provider abstraction across all 4 dimensions**
LLM, embedding, reranker, and observability are all swappable via `.env`. This was built incrementally (LLM first, then the others) but the pattern was consistent. At six LLM providers, four embedding providers, four rerankers, and three observability providers, this is genuine multi-cloud support, not a marketing claim.

**Config-driven behaviour with zero hardcoded thresholds**
Scoring thresholds, quality tier settings, approval tier values, confidence floors, and audit retention are all in YAML or `org_settings`. The pattern is consistent and reviewable. An enterprise customer can change scoring behaviour without raising a support ticket.

**Grounding as a hard contract**
Making the grounding quote a mandatory field — enforced by the Critic with a HARD block — is the right call for a high-stakes decision system. The whitespace normalisation fix for PDF table cells is a non-obvious but critical detail that shows the system has been tested against real documents, not just synthetic ones.

### What is adequate but could be stronger

**LangGraph state design**
The state passed between agents works, but a more sophisticated design would use finer-grained checkpointing — saving state after every agent, not just at failure. The current implementation loses pipeline state on exception. Adding LangGraph's built-in `MemorySaver` or a PostgreSQL checkpoint store would enable true pipeline resume.

**Parallel vendor evaluation**
`parallel_vendors: true` is in org_settings, but full parallelism in the LangGraph topology was added after the core pipeline was built. True parallel evaluation (all vendors running concurrently, not sequentially) requires careful handling of shared PostgreSQL writes. This is in the backlog — the current state is sequential with a config toggle that's not yet fully wired.

**Rate limiter coverage**
`rate_limiter.py` with exponential backoff handles LLM 429 errors. But there is no circuit breaker — if the LLM provider is hard-down (500 errors, not rate limits), the pipeline retries 5 times before failing. A circuit breaker pattern would fail fast and fallback to an alternative provider automatically.

### What needs improvement

**Table-aware PDF parsing**
`LlamaIndex SimpleDirectoryReader` does not handle complex PDF tables well. This is the single largest source of extraction failures — cells split across lines produce garbled text that the LLM cannot reliably extract from. `pdfplumber` or `pymupdf4llm` would fix this. It is in the Tier 1 backlog but has not been built.

**Extraction via tool_use / function-calling**
Extraction currently uses prompt-based JSON (`{"type": "json_object"}`), which breaks on Modal/vLLM (xgrammar crash) and produces inconsistent JSON on some Anthropic prompts. The native `tool_use` / function-calling API is provider-portable and eliminates the JSON parsing fragility. This is a meaningful reliability improvement.

---

## 2. Retrieval Quality

### Quantitative Assessment

| Component | Status | Evidence |
|---|---|---|
| Hybrid search (dense + sparse RRF) | Implemented and verified | `qdrant_client.py` — both vector types present |
| HyDE | Implemented | `app/core/hyde.py` — 3 domain templates |
| Query rewriting | Implemented | `app/core/query_rewriter.py` |
| BGE CrossEncoder reranking | Implemented | `app/core/reranker_provider.py` |
| Retrieval Critic (adequacy check) | Implemented | `app/core/retrieval_critic.py` |
| Held-out test set benchmark | Not done | No annotated test set exists yet |
| MRR@10 measurement | Not done | No ground truth evaluation |

**The gap:** The retrieval pipeline is architecturally complete and follows current best practices. What is missing is a held-out evaluation set with annotated ground truth. Without this, the quality claims (>90% adequacy rate, etc.) are targets, not measurements. Building an annotated test set is the next measurement milestone before production.

---

## 3. Extraction Accuracy

### Quantitative Assessment

| Component | Status | Evidence |
|---|---|---|
| Structured fact extraction (6 fact types) | Implemented | PostgreSQL tables, fact_store.py |
| Grounding quote enforcement | Implemented (HARD block) | critic.py |
| Whitespace normalisation fix | Implemented | extraction.py — re.sub normalisation |
| Extraction Critic (LLM-based adequacy) | Implemented | extraction_critic.py |
| Retry on low confidence | Implemented | 1 retry, configurable |
| Held-out accuracy benchmark | Not done | No annotated test set |
| Hallucination red team test | Not done | No adversarial injection test set |

**The gap:** Same as retrieval — the mechanism is complete but the measurement is not. The grounding quote check is a strong structural guarantee, but it only catches the case where the LLM fabricates text not in the source. It does not catch the case where the LLM reads the source correctly but extracts the wrong field (e.g., extracts Public Liability when the criterion asks for Professional Indemnity — both are present in the document).

The Extraction Critic is designed to catch this, but it has not been tested against a labelled adversarial set.

---

## 4. Evaluation & Scoring Quality

### Quantitative Assessment

| Component | Status | Evidence |
|---|---|---|
| Rubric-based scoring from PostgreSQL facts | Implemented | evaluation.py |
| Config-driven criteria and weights | Implemented | product.yaml + org_settings |
| Confidence scoring with retry | Implemented | confidence_retry_threshold: 0.75 |
| Score band classification | Implemented | score_bands in product.yaml |
| Score consistency test (5× same input) | Not done | No regression test |
| Human expert calibration | Not done | No expert annotation set |
| Bias audit | Not done | No diverse vendor test set |

---

## 5. CEO Dashboard & Product Completeness

| Feature | Status | Notes |
|---|---|---|
| Global RFP active view | Implemented (Next.js) | Real data from evaluation_runs table |
| Total committed spend | Implemented | SUM from evaluation_decisions |
| Duplicate vendor alert | Implemented | Cross-run vendor_id match |
| Pricing anomaly alert | Implemented | Cross-region >15% delta |
| Department / region filter | Implemented | RBAC-scoped filter |
| Drill-down to evaluation report | Implemented | PDF report link |
| Vendor concentration risk | Not yet built | Listed in roadmap Q4 2026 |
| Real-time WebSocket push | Not yet built | Currently polling refresh |
| Mobile-responsive | Unknown | Not tested on mobile |

---

## 6. Production Readiness

| Dimension | Rating | Notes |
|---|---|---|
| Multi-tenancy isolation | Strong | Two-layer: JWT + RLS + Qdrant filter |
| Audit trail | Strong | Immutable AuditOverride, INSERT-only |
| Observability | Good | LangSmith + LangFuse + rate monitor |
| CI/CD pipeline | Weak | No automated CI/CD configured |
| Automated test suite | Partial | contract_tests.py, checkpoint_runner.py — unit/integration tests not yet comprehensive |
| Load testing | Not done | No locust / k6 load test run |
| Security testing | Partial | RLS verified, no penetration test |
| Cloud deployment | Not done | Local only — Modal SSL blocker |
| SOC 2 / ISO 27001 | Not done | Roadmap Q4 2026 |

**Honest summary:** The platform is production-quality in design and architecture. It is not yet in production — the cloud deployment is blocked by a Modal SSL/VPN issue, and the automated test suite and CI/CD pipeline are incomplete. This is a strong late-stage MVP, not a shipped product.

---

## 7. Overall Technical Assessment

| Dimension | Score | Rationale |
|---|---|---|
| Architecture maturity | 9/10 | 9-agent pipeline, Critic topology, two-layer storage, provider abstraction — all correct |
| RAG sophistication | 8/10 | Hybrid search, HyDE, query rewriting, CrossEncoder — state of the art. Missing: held-out benchmark |
| Production thinking | 8/10 | Multi-tenancy, audit trail, RBAC, rate limiting, observability — all present |
| Governance / responsible AI | 9/10 | Grounding enforcement, human override, EU AI Act classification, ISO 42001 alignment |
| Product thinking | 9/10 | CEO dashboard, stakeholder map, personas, OKRs, competitive analysis — full product lifecycle coverage |
| Documentation quality | 9/10 | 30+ documents across 6 lifecycle phases — exceptional for a solo project |
| Test coverage | 5/10 | Contract tests and checkpoints are strong. Unit/integration/load tests are incomplete |
| Cloud deployment | 4/10 | Not yet deployed to cloud — Modal blocked, no CI/CD. Strong design, weak execution evidence |
| Benchmarked AI quality | 3/10 | No held-out evaluation set, no annotated ground truth, no red team results |
| **Overall** | **7.5/10** | Strong design and product scope. The known gaps (test coverage, cloud deployment, held-out benchmarks) are the immediate next priorities. |
