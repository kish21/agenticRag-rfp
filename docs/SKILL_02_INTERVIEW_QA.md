# Skill 02 — Interview Questions and Answers

This document prepares you for technical interviews — FDE roles, AI engineer roles, and solution architect roles. Questions are grouped by theme. For each question there is a direct answer, then a "what to add if they push deeper" section.

---

## Section 1 — System Design

---

**Q: You have 9 agents in your pipeline. How do you prevent one agent's bad output from corrupting the rest of the run?**

**A:**
Every agent is followed immediately by the Critic Agent — a separate validation function that programmatically checks the output before it proceeds. The Critic produces its own typed output (`CriticOutput`) with four possible verdicts: APPROVED, APPROVED_WITH_WARNINGS, BLOCKED, or ESCALATED.

For hard failures — like a vendor being rejected with no evidence citations, or a grounding quote that doesn't appear in the source text — the Critic returns BLOCKED and the pipeline stops. For soft issues, it passes with a warning that's visible in the final report. Nothing downstream ever sees a corrupt output because the Critic is the gate between every stage.

**Push deeper:**
The Critic's grounding verification is deliberately programmatic, not LLM-based. We do a literal string search: does the `grounding_quote` appear as a substring in the source chunk text? An LLM can hallucinate a convincing quote. A string search cannot be fooled. For a compliance use case like procurement, that distinction matters.

---

**Q: Why did you define Pydantic models for every single agent input and output? Isn't that over-engineering?**

**A:**
No — it's the opposite. Without typed contracts, a multi-agent system becomes impossible to debug at scale. When Agent 5 (Evaluation) reads data from PostgreSQL that was written by Agent 4 (Extraction), you need to know at development time — not production time — that the shapes match.

More importantly, the validators in the models do real work. The `grounding_quote` validator rejects empty strings at construction time. The `AuditOverride.reason` validator rejects anything under 20 characters. The `EvaluationSetup` validator verifies that scoring criteria weights sum to 1.0 and that every mandatory check references an extraction target that exists. These aren't nice-to-haves — they're compliance rules encoded in the type system.

The cost is about 400 lines of model definitions. The benefit is that runtime type errors in a 9-agent pipeline are essentially eliminated.

**Push deeper:**
Pydantic v2 uses Rust under the hood for validation — it's extremely fast, not a performance concern. The `@model_validator(mode="after")` pattern lets you run cross-field validation after all individual fields are valid, which is how the weight-sum check works.

---

**Q: How does your system handle multi-tenancy? If Organisation A and Organisation B both use this platform, how do you ensure their data never mixes?**

**A:**
At three levels.

First, every Qdrant search call goes through a wrapper function that mandates `org_id` and `vendor_id` filter conditions. The filter is applied inside `qdrant_client.py`, not in the calling agent code — so an agent cannot accidentally search without the tenant filter even if the developer forgets to add it.

Second, every Pydantic model that represents extracted or evaluated data carries `org_id` and `vendor_id` fields. These are required, not optional — you cannot construct an `ExtractionOutput` without specifying which organisation and vendor it belongs to.

Third, Qdrant collections are named with the convention `{prefix}_{org_id}_{vendor_id}`. Org A's vendor data physically lives in different collections from Org B's.

**Push deeper:**
PostgreSQL multi-tenancy (row-level security by org_id) is handled in Skill 04 when the schema is defined. The Qdrant isolation is foundational from Skill 02 onwards.

---

**Q: Walk me through what happens when a human overrides an AI recommendation in your system.**

**A:**
The only path to changing an evaluation decision is through `create_override_record()` in `override_mechanism.py`. It is the only door.

The function creates an `AuditOverride` model. That model has a `reason` field with a Pydantic validator that rejects strings shorter than 20 characters — you cannot create an override without documented reasoning, and the system enforces that, not a process document.

The record captures: who made the override (`overridden_by`), when (`timestamp`), what the original decision was (`original_decision`), what the new decision is (`new_decision`), and why (`reason`). For high-value contracts there's an `approved_by` field for a second sign-off. The record is then written to the `audit_overrides` table in PostgreSQL.

There is no UPDATE path to evaluation results. Direct database edits bypass the audit trail. This makes the audit log complete and tamper-evident.

**Push deeper:**
This is directly relevant to regulated industries. In financial services procurement, every deviation from an approved AI recommendation would need to be documented for regulatory review. The override mechanism produces exactly that documentation automatically.

---

## Section 2 — Technical Choices

---

**Q: Why Qdrant instead of Pinecone or Weaviate or ChromaDB?**

**A:**
Three reasons: hybrid search, self-hosting, and the API quality.

Qdrant supports both dense and sparse vectors natively in a single collection — one chunk can have an OpenAI embedding for semantic search *and* a BM25 sparse vector for keyword search. Pinecone requires two separate indexes for this. For procurement documents, keyword search is critical: "ISO 27001" should always match exactly, not just semantically.

Qdrant can be self-hosted with Docker, which matters for enterprise customers who cannot send contract data to a third-party SaaS. Pinecone is cloud-only.

ChromaDB was removed from this stack specifically because it doesn't support production multi-tenancy well — there's no built-in tenant isolation at the query level.

**Push deeper:**
`qdrant-client` 1.10+ deprecated `client.search()` in favour of `client.query_points()`. This is a silent API change — old code still works but behaviour changed. This is the kind of version-specific gotcha that matters when you're building on top of fast-moving open source projects.

---

**Q: You have a rate limiter in your platform. Walk me through how it works under load.**

**A:**
It's a token bucket implementation. We maintain a deque of request timestamps. Before any LLM call, we count how many timestamps are within the last 60 seconds. If we're at the limit, we calculate exactly how long to wait until the oldest timestamp falls out of the window, then sleep for that duration plus 100ms buffer.

On top of the rate limiter sits exponential backoff via the `tenacity` library. If OpenAI returns a 429 (rate limit) or 500/503 (server error) or a timeout, we wait 2 seconds, then 4, then 8, up to 60 — up to 5 attempts by default (configurable in `.env`).

The rate limit is also configurable: `RATE_LIMIT_REQUESTS_PER_MINUTE` in the environment. A customer with a higher OpenAI tier can increase it without a code change.

**Push deeper:**
The rate limiter uses an async lock (`asyncio.Lock`) so it's safe for concurrent agents — if two agents try to acquire simultaneously, one waits. There's no double-counting.

---

**Q: Your planner creates deterministic tasks rather than using an LLM to generate them. Isn't that limiting?**

**A:**
Intentionally, at this stage. The Planner's job is to guarantee that every mandatory check and scoring criterion has a corresponding task before a single API call is made. If an LLM generates the task list, there's no reliable way to verify that guarantee — you'd have to trust that the LLM didn't accidentally skip a criterion.

By creating tasks programmatically from `EvaluationSetup`, we can call `validate_plan()` and mathematically prove coverage. Task IDs encode their content (`task-check-MC001`, `task-score-CR003`), so the validator can parse them and confirm every check and criterion is represented.

The LLM gets involved in the *execution* of tasks — retrieving chunks, extracting facts, scoring against rubrics. The *planning* — what needs to happen — is deterministic by design.

**Push deeper:**
This is the principle of separating what to do (planning, deterministic) from how to do it (execution, LLM-assisted). It also makes the system testable: you can write a unit test that creates an EvaluationSetup with 3 checks and verify the plan always produces exactly 3 mandatory_check tasks.

---

## Section 3 — FDE-Specific Questions

---

**Q: A customer comes to you and says "we tried an AI procurement tool before and it gave us wrong answers and we can't tell why." How does your platform address that?**

**A:**
Every single claim in the final report is traced back to a source quote. The `ExplanationOutput` model contains `grounded_claims` — each one has the claim text, the exact quote from the vendor document, the chunk ID it came from, the filename, and the page number. If the customer asks "why did you say Vendor A has ISO 27001?", we can show them the exact sentence in the document we extracted it from.

The Critic Agent also checks grounding completeness before the report is finalised. If fewer than 70% of claims are grounded, it raises a HARD flag and blocks the report from being sent. The report cannot be delivered if it contains too many unverifiable claims.

On the extraction side, every fact has a `grounding_quote` field that is validated programmatically — if the extracted quote doesn't appear verbatim in the source chunk, the Critic flags it as a potential hallucination before it reaches scoring.

---

**Q: A large enterprise customer wants to run this on Azure, not Modal. What changes?**

**A:**
Very little in the application code. The `COMPUTE_PROVIDER` setting in `.env` is the switch — the platform already has an abstraction in `compute_provider.py` that maps providers to their extraction function. Azure Functions, AWS Lambda, and GCP Cloud Run are listed as planned providers (Skill 09).

For the LLM side, Azure OpenAI uses the same OpenAI SDK with a different `base_url` and `api_version` — it would need an `azure_openai` option added to `LLM_PROVIDER` in `llm_provider.py`. The change is isolated to that one file.

For vector storage, Qdrant has a managed cloud offering that includes an Azure deployment option. The `QDRANT_HOST` and `QDRANT_PORT` in `.env` point to wherever Qdrant runs — Docker, Qdrant Cloud, or a self-managed VM.

**Push deeper:**
Azure AI Foundry specifically provides managed versions of OpenAI models with Azure Active Directory authentication, content filtering, and compliance certifications (SOC 2, ISO 27001). A customer on Azure AI Foundry would use `LLM_PROVIDER=azure_openai` and their Foundry endpoint — the rest of the platform is unchanged.

---

**Q: How would you demo this platform to a customer in 15 minutes?**

**A:**
I'd show four things in sequence:

1. **The contract layer** — show `EvaluationSetup` in action. Customer defines: 3 mandatory checks, 4 scoring criteria with weights that sum to 1.0. The model validates the weights live. "Your criteria are now the system's constitution — nothing gets evaluated that isn't here."

2. **The safety gate** — run `critic_after_decision()` against a scenario where a vendor is rejected with no evidence. Show it return BLOCKED. "The system cannot reject a vendor without documented evidence. That's not a policy — it's enforced by code."

3. **The audit trail** — try to create an override with a one-word reason. Show the validation error. Create one with a proper reason. Show the override record. "Every deviation from the AI recommendation is permanently recorded with who, when, and why."

4. **The grounding check** — show an `ExtractedFact` with a quote that doesn't match the source text, show the Critic flag it as hallucination. Then show a legitimate extraction with a real quote. "The system does not trust its own output. It checks it."

In 15 minutes I haven't shown them a single LLM call — but I've shown them that the system has controls that most AI procurement tools don't even think about.

---

**Q: A customer asks — what happens if the AI gets it wrong and we select the wrong vendor?**

**A:**
Two things. First, the system is designed to give you the evidence to catch that yourself — every recommendation in the report links back to the exact text in the vendor documents. A 10-minute review of the top-ranked vendor's citations should surface any misinterpretation.

Second, the override mechanism exists precisely for this scenario. If a procurement manager reviews the output and disagrees with a ranking, they use the override to record their decision and the reason. The system doesn't fight them — it accommodates human judgement while preserving the audit trail.

What the system prevents is a *different* failure: a recommendation being changed without documentation, or a vendor being rejected without evidence. Those are the changes that create legal and regulatory exposure.

---

## Section 4 — Harder Technical Questions

---

**Q: What's the difference between a HARD flag and a SOFT flag in your Critic Agent? Who decides which is which?**

**A:**
HARD flags block the pipeline — the current agent's output is not passed to the next stage. SOFT flags allow the pipeline to continue but append warnings to the output.

The classification is not arbitrary — it follows a principle: HARD if acting on the output would cause incorrect decisions that cannot be corrected downstream. SOFT if a human can review and correct later.

Examples of HARD: grounding quote not in source (hallucination), rejection without evidence citations (legal exposure), document quality score below 0.4 (output probably garbage). Examples of SOFT: quality score between 0.4 and 0.65 (marginal quality, proceed with care), duplicate document (skip re-ingestion, use existing).

The `hard_flag_blocks_pipeline` setting in `.env` is a global switch — you can turn off hard blocking in development mode. In production it must be `true`.

---

**Q: How does your system prevent the same vendor document from being processed twice?**

**A:**
The Ingestion Agent produces an `IngestionOutput` with a `content_hash` field — a hash of the document content. On re-submission, the system checks if a collection with that hash already exists. If it does, the Critic flags it as a SOFT flag with `auto_resolvable=True` and `status="duplicate"`.

Auto-resolvable means the pipeline can handle it without human input — skip re-ingestion, proceed with existing data. The vendor doesn't get double-counted.

---

**Q: What would you change if you needed this system to process 1,000 vendors simultaneously instead of 10?**

**A:**
Three things.

Rate limiting needs to scale horizontally — currently the token bucket is in-process memory. For 1,000 vendors you'd need a Redis-backed distributed rate limiter so multiple workers share one counter.

The task DAG would need a proper queue. Currently tasks are sequential within one process. For 1,000 vendors you'd use a message queue (Celery, or Modal's native parallelism) — each vendor's extract/evaluate tasks run in parallel workers.

Qdrant collections per vendor would need to be namespaced differently at scale — 1,000 collections is fine, 100,000 starts requiring Qdrant collection management overhead. A per-org collection with vendor_id as a payload filter is the migration path.

**Push deeper:**
Modal — the compute provider already integrated — handles burst parallelism natively. `extract_pdf_on_modal()` can be called 1,000 times simultaneously; Modal provisions the containers. The rate limiter is the real bottleneck, not the compute.

---

**Q: Why did you separate PostgreSQL (structured facts) and Qdrant (chunks) instead of using one database?**

**A:**
They serve fundamentally different access patterns.

Qdrant is optimised for approximate nearest-neighbour search over high-dimensional vectors. It is excellent at "find the 20 most semantically similar chunks to this query." It is terrible at "give me the exact ISO certification expiry date for Vendor A."

PostgreSQL is optimised for exact lookups, joins, and aggregations. "Give me all vendors where ISO 27001 is current AND total contract value under £500k AND project references in financial services" is a single SQL query. In Qdrant, that's multiple searches filtered post-hoc.

The Evaluation Agent deliberately reads PostgreSQL facts, not Qdrant chunks. By the time evaluation runs, the facts have been extracted, validated, and stored with structured fields. Using Qdrant at evaluation time would mean re-running retrieval and re-extracting during scoring — slower, less reliable, and harder to audit.

---

## Section 5 — Questions to Ask the Interviewer

These show strategic thinking, not just technical execution:

1. "When your customers override AI recommendations, what percentage of the time does the AI turn out to have been correct? Do you track that?"

2. "What's the typical document volume per vendor in your largest customer deployment — are we talking 10-page responses or 200-page RFP responses?"

3. "Has a customer ever had a procurement challenge — a vendor disputing their rejection — and needed to produce audit evidence? What did that look like?"

4. "For customers in regulated industries, is the compliance audit trail a checkbox requirement or something procurement teams actually use?"

5. "How do you currently handle the case where different departments within one organisation have completely different evaluation criteria?"
