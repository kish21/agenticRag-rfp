# Product Documentation Index
**Enterprise Vendor Governance & Spend Intelligence Platform**
*Last updated: 2026-05-14*

---

## Phase 1 — Strategy & Discovery

| Document | Description |
|---|---|
| [Business Case](phase1_strategy/01_business_case.md) | ROI analysis, problem statement, financial justification |
| [Stakeholder Map](phase1_strategy/02_stakeholder_map.md) | CEO, CFO, Procurement Manager, Legal, IT Admin personas and influence matrix |
| [Current State Process](phase1_strategy/03_current_state_process.md) | Before/after process map, baseline metrics, pain points |
| [User Personas](phase1_strategy/04_user_personas.md) | 5 detailed personas: CEO Sarah, Procurement Manager James, Dept Head Priya, CFO Marcus, IT Admin Liam |
| [Competitive Analysis](phase1_strategy/05_competitive_analysis.md) | vs Icertis, Ironclad, Coupa, SAP Ariba, raw LLM — positioning and pricing |

---

## Phase 2 — Requirements

| Document | Description |
|---|---|
| [PRD](phase2_requirements/01_prd.md) | Goals, non-goals, user stories, success metrics, constraints |
| [Functional Requirements](phase2_requirements/02_functional_requirements.md) | FR-01 to FR-11: ingestion, extraction, retrieval, evaluation, CEO dashboard, audit |
| [Non-Functional Requirements](phase2_requirements/03_non_functional_requirements.md) | NFR-01 to NFR-08: performance, reliability, scalability, security, compliance |
| [OKRs](phase2_requirements/04_okrs.md) | 4 Objectives, 15 Key Results for Q2–Q3 2026 + Q4 2026 draft |
| [KRAs](phase2_requirements/05_kras.md) | 9 Key Result Areas mapped to files, owners, and success criteria |
| [Data Requirements](phase2_requirements/06_data_requirements.md) | Input formats, storage schemas, data lineage, retention policy, GDPR |

---

## Phase 3 — Architecture & Design

| Document | Description |
|---|---|
| [System Architecture](phase3_architecture/01_system_architecture.md) | Full architecture diagram, 9-agent overview, data flows, multi-tenancy design |
| [Agent Tech Stack](phase3_architecture/02_agent_tech_stack.md) | Every agent: exact tech, libraries, models, why — agent by agent |
| [Configuration Guide](phase3_architecture/03_configuration_guide.md) | .env, product.yaml, platform.yaml, org_settings API — all 4 enterprise profiles |
| [Security & Trust Model](phase3_architecture/04_security_trust_model.md) | JWT auth, RBAC, two-layer tenant isolation, hallucination defence, audit integrity |
| [ADR-001: Qdrant over ChromaDB](phase3_architecture/adrs/ADR-001-qdrant-over-chroma.md) | Why hybrid search required Qdrant |
| [ADR-002: Two Storage Layers](phase3_architecture/adrs/ADR-002-two-storage-layers.md) | Why Evaluation reads PostgreSQL, not Qdrant |
| [ADR-003: LangGraph over CrewAI](phase3_architecture/adrs/ADR-003-langgraph-orchestration.md) | Typed state, enforced topology, checkpointing |
| [ADR-004: BGE Reranker Default](phase3_architecture/adrs/ADR-004-bge-reranker-default.md) | Free local reranker vs. Cohere paid API |
| [ADR-005: Modal GPU Inference](phase3_architecture/adrs/ADR-005-modal-gpu-inference.md) | Qwen 2.5 72B on A100 vs. OpenRouter vs. Ollama local |

---

## Phase 4 — Build & Quality

| Document | Description |
|---|---|
| [Evaluation Framework](phase4_build/01_evaluation_framework.md) | AI quality metrics: retrieval, extraction, scoring, report — targets and how to measure |
| [Prompt Registry](phase4_build/02_prompt_registry.md) | All 6 prompts (retrieval critic, extraction critic, HyDE, query rewrite, extraction, scoring) with revision history |
| [Observability Plan](phase4_build/03_observability_plan.md) | LangSmith + LangFuse events, dashboards, rate monitor, cleanup job |
| [Test Plan](phase4_build/04_test_plan.md) | Unit, integration, contract, checkpoint, load, security tests — all commands |

---

## Phase 5 — Deployment & Governance

| Document | Description |
|---|---|
| [Deployment Runbook](phase5_deployment/01_deployment_runbook.md) | Local dev, Modal deploy, cloud production, tenant onboarding, JWT rotation, rollback |
| [Incident Response](phase5_deployment/02_incident_response.md) | P0–P3 playbooks: all-pipelines-down, data breach, rate limit, Critic false block, Modal cold start |
| [AI Governance](phase5_deployment/03_ai_governance.md) | EU AI Act classification, hallucination defence layers, bias risks, ISO 42001 alignment, pre-deployment checklist |
| [RBAC Design](phase5_deployment/04_rbac_design.md) | 8 roles, JWT claims, permission matrix, approval tier vs. RBAC, user management API |
| [Multi-Cloud Deployment Guide](phase5_deployment/05_multi_cloud_deployment_guide.md) | Step-by-step deploy for Modal, Azure, AWS, GCP, Air-gapped — with actual CLI commands |

---

## Phase 6 — Post-Launch

| Document | Description |
|---|---|
| [Retrospective](phase6_post_launch/01_retrospective.md) | What went well, harder than expected, what we'd design differently, key lessons |
| [Product Roadmap](phase6_post_launch/02_product_roadmap.md) | Q3 2026 pilot → Q4 2026 fine-tuning → 2027 market expansion |
| [Capacity Planning](phase6_post_launch/03_capacity_planning.md) | Qdrant / PostgreSQL / Modal / API costs at pilot / 10 customers / 100 customers |
| [Project Evaluation](phase6_post_launch/04_project_evaluation.md) | Honest technical scorecard — strengths, gaps, ratings per dimension, interview prep |

---

## Quick Reference

### The 9 Agents
```
1. Planner    → deterministic task DAG
2. Ingestion  → LlamaIndex → Qdrant (dense + sparse)
3. Retrieval  → HyDE + hybrid search + BGE reranker
4. Extraction → LLM → PostgreSQL (grounded facts)
5. Evaluation → PostgreSQL facts → rubric scores
6. Comparator → SQL join cross-vendor → ranking
7. Decision   → contract value → approval tier routing
8. Explanation → cited report → PDF
9. Critic     → runs after EVERY agent → HARD/SOFT/LOG/ESCALATE
```

### The 4 Provider Abstractions
```
LLM_PROVIDER=         openai | anthropic | openrouter | ollama | azure | modal
EMBEDDING_PROVIDER=   openai | azure | local | modal
RERANKER_PROVIDER=    bge | cohere | colbert | none
OBSERVABILITY_PROVIDER= langfuse | stdout | none
```

### The 3 Documents That Matter Most for Interviews
1. [PRD](phase2_requirements/01_prd.md) — validates you understand the problem
2. [Agent Tech Stack](phase3_architecture/02_agent_tech_stack.md) — shows depth across the full pipeline
3. [ADR log](phase3_architecture/adrs/) — proves you evaluated tradeoffs, not just followed tutorials
