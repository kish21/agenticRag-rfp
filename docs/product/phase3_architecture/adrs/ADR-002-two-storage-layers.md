# ADR-002: Two Storage Layers (Qdrant + PostgreSQL) — Both Required
*Date: 2026-03-20 | Status: Accepted*

## Context

After completing the retrieval layer (Qdrant), we needed to decide where the Evaluation Agent reads its input from. Two options:
1. Evaluation reads raw text chunks from Qdrant (single storage layer)
2. Extraction Agent writes structured facts to PostgreSQL; Evaluation reads from there (two storage layers)

## Decision

Maintain two storage layers. Qdrant for raw chunk embeddings; PostgreSQL for extracted structured facts. The Evaluation Agent reads PostgreSQL — never Qdrant chunks.

## Rationale

### Why not read chunks in Evaluation?

The Evaluation Agent needs to score vendors against criteria like:
- "Does vendor have ISO 27001 certification with certificate number?"
- "Is professional indemnity insurance ≥ £5M?"
- "Is uptime SLA ≥ 99.9%?"

These questions require **typed comparison** (numeric, date, string equality). A raw text chunk cannot be queried with SQL. The LLM would have to re-extract the fact every time it evaluates — with no consistency guarantee and no audit trail of what was extracted.

### Why PostgreSQL?

| Requirement | Qdrant (chunks) | PostgreSQL (facts) |
|---|---|---|
| SQL join across vendors | No | Yes — `JOIN ON org_id + run_id` |
| Typed field comparison (numeric, date) | No | Yes — `WHERE coverage_amount >= 5000000` |
| Row-Level Security (tenant isolation) | Filter-based | RLS at DB layer |
| Audit trail of what was extracted | No | Yes — every row has `source_chunk_id`, `grounding_quote` |
| Cross-vendor ranking in Comparator | Requires materialising all chunks | Single SQL query |
| GDPR data deletion | Delete collection | DELETE WHERE org_id = ? |

### The Lineage Link

Every PostgreSQL fact row has a `source_chunk_id` that links back to the Qdrant chunk it was extracted from. This preserves the full lineage: fact → chunk → page → source document.

## Consequences

- Extraction Agent must write to PostgreSQL as part of every run — no batching, no delay
- Evaluation Agent never queries Qdrant directly
- `app/db/fact_store.py` owns all PostgreSQL writes
- `app/db/schema.sql` defines the typed tables (extracted_certifications, extracted_insurance, etc.)
- Re-ingestion without re-extraction is valid; re-extraction always overwrites PostgreSQL facts for that run

## Rejected Alternatives

- **Single storage (Qdrant only):** Evaluation would re-extract on every LLM call — inconsistent, no typed comparison, no cross-vendor SQL join, no structured audit trail
- **Single storage (PostgreSQL only):** Lose the semantic search capability — text similarity retrieval requires vector embeddings
