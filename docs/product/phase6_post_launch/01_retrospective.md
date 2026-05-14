# Retrospective — Platform Build (Skills 01–09)
*Version 1.0 — 2026-05-14*

---

## What We Built

A 9-agent AI pipeline for enterprise vendor evaluation, with:
- CEO-facing spend intelligence dashboard
- Multi-tenant, multi-region, multi-department architecture
- Critic agent hard-block guardrails on every agent output
- Configurable LLM, embedding, reranker, and observability providers
- Human override with immutable audit trail
- 65/66 checkpoints passed

---

## What Went Well

### Architecture decisions that proved correct

**Two storage layers (Qdrant + PostgreSQL)**
The decision to write structured facts to PostgreSQL and have Evaluation read from there — not raw Qdrant chunks — was the right call. The Comparator's SQL join across vendors is clean, fast, and auditable. This would have been impossible with a single vector store.

**Provider abstraction pattern**
The `call_llm()` / `embedding_provider` / `reranker_provider` abstraction means customers can switch from OpenAI to Azure in a single `.env` change. This has already been tested across 5 provider combinations. No agent file needed changes.

**Critic Agent as a first-class citizen**
Making the Critic a mandatory node in the LangGraph topology — not an optional post-processing step — meant hallucination problems surfaced early, during build, not in production. The Retrieval Critic and Extraction Critic sub-modules caught issues that would have produced silently wrong evaluations.

**Config-driven behaviour**
All agent thresholds, quality tier settings, approval tiers, and score bands live in YAML or `org_settings`. No hardcoded business logic in agent files. This allowed rapid iteration on scoring without touching agent code.

---

## What Was Harder Than Expected

### PDF table parsing
PDF cells on separate lines caused grounding quote checks to fail. The whitespace normalisation fix (`re.sub(r'\s+', ' ', text).strip()`) was a non-obvious but critical fix. Any future PDF parsing change must run the grounding regression tests immediately.

### LangFuse SDK migration (2.x → 4.x)
LangFuse 4.x was a near-complete SDK rewrite. The migration consumed significant time. The solution (building `observability_provider.py` as an abstraction layer) turned this into an advantage — customers can now swap observability providers via `.env`.

### Modal SSL / VPN issue
Modal gRPC is blocked by corporate VPN. The Modal LLM deployment is functionally complete (`serve_llm_on_modal`) but not yet deployed. This is an infrastructure constraint, not a code problem. Resolution: deploy off VPN or configure Modal HTTPS-only mode.

### Qdrant API deprecation
`client.search()` was deprecated in qdrant-client 1.14.x in favour of `client.query_points()`. Caught during build — all usage updated in `qdrant_client.py`. Worth noting for any future qdrant-client upgrades.

### `ragatouille` removal
ColBERT via `ragatouille` was in the original design. The library became unmaintained during our build cycle. Removed and replaced with `sentence-transformers CrossEncoder` for ColBERT. The BGE CrossEncoder (`bge-reranker-v2-m3`) ended up being the right default anyway.

---

## What We Would Design Differently

### Table-aware PDF parsing from day one
`LlamaIndex SimpleDirectoryReader` handles plain text well but struggles with complex PDF tables. We would start with `pdfplumber` or `pymupdf4llm` for table-rich documents from the beginning, rather than adding it as a Tier 1 backlog item.

### Extraction via tool_use / function_calling from day one
Using the LLM's native function-calling / tool_use for structured extraction (rather than prompt-based JSON) would eliminate JSON parsing fragility. The current `response_format={"type": "json_object"}` approach requires provider-specific handling (Modal/vLLM doesn't support it). Native tool_use is provider-portable.

### Parallel agent evaluation from day one
`parallel_vendors: true` is in org_settings but full parallelism wasn't wired into the LangGraph topology from the start. Adding it later required careful state management to avoid race conditions on shared PostgreSQL writes.

### Domain-specific evaluation criteria templates
Shipping with procurement, HR, IT, and legal criteria templates pre-built would have made the first customer demo faster. We built the config framework perfectly but the content (criteria templates) is still customer-defined.

---

## Key Lessons

1. **Build the Critic Agent first, not last.** It finds problems in every other agent. Building it at the end means you find the problems at the end.

2. **Provider abstraction is worth the upfront cost.** Every provider we added after the first took less than 2 hours. Customers care about this more than any single feature.

3. **Config-driven behaviour is not optional for enterprise.** The first enterprise customer will immediately ask to change scoring thresholds, approval tiers, and quality settings. If these are hardcoded, you are back to engineering for every request.

4. **The CEO dashboard is the product.** The 9-agent pipeline is impressive but invisible to executives. The dashboard is what they buy. It should have been prioritised earlier.

5. **Grounding quotes are not just a nice-to-have.** Every evaluator who saw the extraction view — with verbatim quotes — immediately trusted the system more. Without grounding, the output is opinion. With it, it is evidence.
