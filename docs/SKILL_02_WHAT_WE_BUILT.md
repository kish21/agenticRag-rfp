# Skill 02 — What We Built, Why It Matters, and Which Layers It Touches

## The one-sentence version

Skill 02 is the **governance backbone** of the entire platform — before any document is read or any vendor is scored, Skill 02 defines the contracts every agent must honour, the rate controls that prevent failures at scale, the Critic that audits every single output, and the audit trail that makes every human override defensible in court.

---

## The seven files and what each one does

### 1. `app/core/output_models.py` — The Contract Layer

**What it is:** Every Pydantic model for every input and output in the system. 400+ lines. Every agent in the pipeline is typed here.

**Why it matters:**
- A multi-agent system without strict contracts is a debugging nightmare. When Agent 3 passes data to Agent 5, you need to know *exactly* what shape that data is — not by reading code, but because the runtime enforces it.
- Every extracted fact carries a `grounding_quote` field that is **validated at construction time** — if an LLM tries to return an empty quote, Pydantic rejects it before it ever reaches the database.
- The `EvaluationSetup` model (added at end of session) is the customer's declared intent. Nothing gets evaluated that isn't defined here. This prevents the platform from "wandering" and evaluating things no one asked for.
- `AuditOverride` has a minimum 20-character reason validator. You cannot create an override record without documented reasoning — the model itself enforces compliance.

**Layers it touches:**
| Layer | How |
|---|---|
| Business Logic | Defines what facts matter, what scores mean, what compliance looks like |
| Data | Shapes what goes into PostgreSQL and Qdrant |
| API | FastAPI routes receive and return these models |
| Governance | Validators enforce grounding, weight sums, override reasons |

**Key models and their purpose:**

| Model | Purpose |
|---|---|
| `EvaluationSetup` | Customer's declared criteria — drives the entire run |
| `ExtractionTarget` | One thing to pull from vendor docs |
| `MandatoryCheck` | Binary pass/fail gate — vendor rejected if fails |
| `ScoringCriterion` | Weighted dimension (weights validated to sum to 1.0) |
| `ExtractedFact` | Generic extracted value linked back to ExtractionTarget |
| `PlannerOutput` | The typed task DAG the Planner produces |
| `CriticOutput` | Verdict after every agent — APPROVED / BLOCKED / ESCALATED |
| `AuditOverride` | Every human decision change, permanently recorded |
| `ExtractionOutput` | All facts extracted from one vendor's documents |
| `DecisionOutput` | Final shortlist + rejections with evidence citations |
| `ExplanationOutput` | Grounded report — every claim traced to source text |

---

### 2. `app/core/rate_limiter.py` — The Reliability Layer

**What it is:** Token bucket rate limiter + exponential backoff retry decorator. Sits between every agent and every LLM API call.

**Why it matters:**
- Without rate limiting, evaluating 20 vendors simultaneously sends 20 × N concurrent API calls. At ~50 RPM (OpenAI default tier), this fails mid-run around vendor 6. The run produces partial results. No one trusts partial results.
- Exponential backoff means a 429 rate-limit error from OpenAI becomes a 2-second wait, then 4, then 8 — automatically, without the agent knowing anything failed.
- `call_with_backoff()` is the function `llm_provider.py` calls internally, meaning the rate limiter applies to **all four LLM providers** (OpenAI, Anthropic, OpenRouter, Ollama) through a single code path.

**Layers it touches:**
| Layer | How |
|---|---|
| Infrastructure | Wraps all outbound API calls |
| Reliability | Converts transient failures into automatic retries |
| Cost control | Prevents accidental quota exhaustion |

**The key insight:** `max_retry_limit` is in `config.py` / `.env` — the number of retries is a business decision, not a code decision. A customer with a higher API tier can raise it without touching code.

---

### 3. `app/core/qdrant_client.py` — The Vector Store Layer

**What it is:** Wrapper around the Qdrant vector database client. Handles collection creation, dual-vector upserts, and tenant-isolated search.

**Why it matters:**
- Every search call enforces `org_id` AND `vendor_id` filters. It is architecturally impossible for Org A to accidentally retrieve Org B's vendor documents — the filter is applied inside the wrapper, not in the calling code.
- Uses `query_points()` not the deprecated `search()` method — this matters because qdrant-client 1.10+ silently changed behaviour on the old method.
- Supports **both dense (semantic) and sparse (BM25 keyword) vectors** per chunk. This is the foundation for hybrid search in Skill 03b — dense finds conceptually similar content, sparse finds exact keyword matches (e.g. "ISO 27001" never misses because of semantic drift).

**Layers it touches:**
| Layer | How |
|---|---|
| Data | Primary document retrieval store |
| Infrastructure | Docker-managed Qdrant instance |
| Multi-tenancy | org_id + vendor_id isolation enforced at the query level |
| Security | No cross-tenant data leakage possible by design |

---

### 4. `app/agents/planner.py` — The Orchestration Layer

**What it is:** The Planner Agent. Takes an `EvaluationSetup` and produces a fully typed task DAG — a list of tasks in the correct order with explicit dependencies.

**Why it matters:**
- The Planner is the **only place** where the evaluation scope is translated into work. Every other agent is reactive — it receives a task and does it. The Planner is the only one that sees the full picture.
- Because tasks are deterministic (not LLM-generated), `validate_plan()` can **programmatically verify** that every mandatory check and scoring criterion has a corresponding task. If a check is missing, the plan is rejected before a single API call is made.
- Task IDs encode their content: `task-check-MC001` tells you this task covers mandatory check MC001. This is not a naming convention — it is a machine-readable contract that `validate_plan()` parses.
- Dependencies are explicit: scoring tasks cannot start until all mandatory check tasks complete. Comparison cannot start until all scoring is done. The DAG prevents out-of-order execution.

**Layers it touches:**
| Layer | How |
|---|---|
| Business Logic | Translates customer intent (EvaluationSetup) into execution plan |
| Orchestration | Defines task ordering and dependencies for LangGraph |
| Governance | validate_plan() ensures nothing was missed before work starts |

**The key insight:** The Planner failing hard is *desirable*. If a mandatory check has no corresponding task, you want to know before spending £200 in API credits on a run that would produce a legally incomplete result.

---

### 5. `app/agents/critic.py` — The Governance Layer

**What it is:** Six functions — one for each agent stage — that run after every agent output and produce a `CriticOutput` with a verdict of APPROVED, APPROVED_WITH_WARNINGS, BLOCKED, or ESCALATED.

**Why it matters:**
- This is the most important safety mechanism in the system. Without the Critic, a hallucinated grounding quote would flow straight into the evaluation, score the vendor, and appear in the final report — all without anyone knowing.
- Grounding verification is **programmatic, not LLM-based**. `critic_after_extraction()` does a literal string search: if the `grounding_quote` is not a substring of the source chunk text, it raises a HARD flag. An LLM cannot lie its way past this check.
- The "rejection without evidence" check (`critic_after_decision()`) is a **legal protection** — rejecting a vendor in a formal procurement process without documented evidence is legally actionable. The Critic blocks this automatically.
- Hard flags stop the pipeline. Soft flags proceed with warnings. This is configurable via `hard_flag_blocks_pipeline` in `.env`.

**Layers it touches:**
| Layer | How |
|---|---|
| Governance | Audits every agent output before it proceeds |
| Legal/Compliance | Blocks rejections without evidence, escalates all-rejected outcomes |
| Data Quality | Programmatic grounding verification catches hallucinations |
| Reliability | Prevents corrupted outputs from reaching later pipeline stages |

**The six Critic functions:**
| Function | What it checks |
|---|---|
| `critic_after_ingestion` | Document quality score, missing requirement sections, duplicates |
| `critic_after_retrieval` | Empty retrieval, no answer-bearing chunks, wrong section types |
| `critic_after_extraction` | Grounding quote present in source, hallucination risk score |
| `critic_after_evaluation` | Implicit-only confirmations on mandatory checks, contradictory evidence |
| `critic_after_decision` | Rejections without evidence citations, all-vendors-rejected escalation |
| `critic_after_explanation` | Grounding completeness <70% blocks report, programmatic quote verification |

---

### 6. `app/core/rfp_confirmation.py` — The Day-One Failure Prevention

**What it is:** Extracts identity fields from an RFP document and formats a confirmation message shown to the user before any evaluation runs.

**Why it matters:**
- The most common real-world failure in procurement AI is evaluating vendor responses against the **wrong RFP**. An organisation uploads last year's RFP by mistake. The platform dutifully scores all vendors against it. Three days later someone notices.
- Two minutes of user confirmation prevents this. The system extracts: reference number, issuing organisation, title, deadline, number of mandatory requirements, number of scoring criteria. A human confirms all six before anything runs.
- This is listed in CLAUDE.md as one of three "day-one failures to build first" — it is prioritised above most features because the cost of getting it wrong is catastrophic.

**Layers it touches:**
| Layer | How |
|---|---|
| User Experience | Explicit confirmation gate before expensive computation |
| Risk Management | Prevents wrong-document evaluations |
| Audit | rfp_confirmed flag is recorded in PlannerOutput |

---

### 7. `app/core/override_mechanism.py` — The Audit Layer

**What it is:** The only permitted way to change an evaluation decision after the pipeline has run. Creates an `AuditOverride` record with mandatory documented reasoning.

**Why it matters:**
- In enterprise procurement, the final shortlist is a legal document. If a procurement manager overrides the AI's recommendation — say, promoting a lower-ranked vendor — that decision must be recorded: who did it, when, what changed, and why, with a minimum reason length enforced at the model level.
- There is no `UPDATE` path. Direct database edits bypass the audit trail. The override mechanism is the only door, and every time it opens, it leaves a permanent record.
- `approved_by` field supports a senior approver workflow — for high-value contracts, overrides can require a second sign-off.

**Layers it touches:**
| Layer | How |
|---|---|
| Compliance | Creates permanent, immutable audit record |
| Legal | Documents every deviation from AI recommendation |
| Data | Writes to audit_overrides table in PostgreSQL |
| Governance | Works alongside Critic Agent to enforce human oversight |

---

## How the seven files connect

```
Customer defines intent
        │
        ▼
EvaluationSetup (output_models.py)
        │
        ▼
run_planner() ──→ validate_plan() checks coverage
        │                    │
        │              FAIL: stop here
        │
        ▼ (task DAG)
Each task executes
        │
        ▼
[Agent produces output typed by output_models.py]
        │
        ▼
Critic runs (critic.py) ──→ BLOCKED: pipeline stops
        │                        │
        │                   SOFT FLAG: proceed with warning
        │
        ▼ (APPROVED)
Next agent receives output
        │
        ▼
...continues through pipeline...
        │
        ▼
Final DecisionOutput
        │
        ├──→ Human reviews
        │         │
        │    Override needed?
        │         │
        │         ▼
        │    create_override_record() (override_mechanism.py)
        │    Reason validated (min 20 chars)
        │    AuditOverride written to PostgreSQL
        │
        ▼
ExplanationOutput → Report
```

All LLM calls in this path go through:
`rate_limiter.py → llm_provider.py → provider SDK`

All vector storage goes through:
`qdrant_client.py → Qdrant (Docker)`

---

## Which architecture layers does Skill 02 touch?

| Layer | Skill 02 contribution |
|---|---|
| **Contract / Schema** | output_models.py — 30+ typed models, all agent I/O defined |
| **Orchestration** | planner.py — task DAG, dependency resolution |
| **Governance** | critic.py — post-agent auditing, grounding verification, escalation |
| **Reliability** | rate_limiter.py — token bucket, exponential backoff, all providers |
| **Vector Store** | qdrant_client.py — hybrid search foundation, tenant isolation |
| **Risk Management** | rfp_confirmation.py — wrong-document prevention |
| **Audit / Compliance** | override_mechanism.py — immutable override trail |

Skills 01 set up the infrastructure (Docker, config, providers).
**Skill 02 defines the rules everything else plays by.**
Skills 03–09 build agents that implement those rules.

---

## What Skill 02 deliberately does NOT do

- Does not connect to any LLM for evaluation (that is Skill 05)
- Does not ingest or embed any documents (that is Skill 03)
- Does not write to PostgreSQL in production (schema is Skill 04)
- Does not build the API routes (started in Skill 01, completed in Skill 09)

This separation is intentional. The contracts, controls, and governance layer must exist and be tested **before** any agent code is written. Every skill from 03 onward inherits from what Skill 02 defines.
