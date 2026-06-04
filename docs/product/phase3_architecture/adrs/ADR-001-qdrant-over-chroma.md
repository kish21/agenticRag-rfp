# ADR-001: Qdrant over ChromaDB as Vector Store
*Date: 2026-03-15 | Status: Accepted (naming convention SUPERSEDED-PENDING — see note)*

> **2026-06-04 (#215 / E215):** The "Collection naming convention: `{org_id}__{vendor_id}`"
> consequence below is **superseded** — collections are now **one per org**
> (`{prefix}_{org_id}`), with vendor scoping handled by the `org_id` + `vendor_id`
> payload filters that already run on every query. The core decision (Qdrant over
> ChromaDB) stands; only the per-vendor collection grain changed, to avoid a
> per-vendor collection-count scaling wall. Cross-org isolation remains a physical
> collection boundary. See `docs/dev/E215_QDRANT_PER_ORG_COLLECTION.md`.

## Context

We need a vector store for storing and retrieving document embeddings. The platform requires:
- Dense (semantic) AND sparse (keyword/BM25) vector support in a single store
- Multi-tenant isolation via metadata filters (org_id + vendor_id)
- Production-grade performance at scale (10M+ vectors per org)
- Self-hosted option for air-gapped enterprise customers

ChromaDB was the initial choice (used in early prototypes).

## Decision

Replace ChromaDB with Qdrant.

## Rationale

| Requirement | ChromaDB | Qdrant |
|---|---|---|
| Sparse vector support (BM25) | No (dense only) | Yes — named vectors, native sparse support |
| Hybrid search (dense + sparse, RRF) | No (requires external fusion) | Yes — built-in RRF fusion |
| Multi-tenant metadata filtering | Partial — single collection per tenant | Yes — filter push-down on any payload field |
| Production throughput | Limited — Python-native, not suited for scale | Yes — Rust core, benchmarked at 1M+ ops/sec |
| Self-hosted option | Yes | Yes |
| Cloud managed option | No | Yes (Qdrant Cloud) |
| Client API stability | Frequent breaking changes | Stable versioned API |

Hybrid search (dense + sparse) is a hard requirement — Cohere and other benchmarks show 10–25% retrieval improvement over dense-only. ChromaDB cannot do this without an external step. Qdrant supports it natively.

## Consequences

- `app/retrieval/qdrant.py` wraps all Qdrant operations
- All queries use `client.query_points()` — not deprecated `client.search()`
- ~~Collection naming convention: `{org_id}__{vendor_id}`~~ → **superseded by #215**: one collection per org `{prefix}_{org_id}`; vendor scoping via payload filter
- Switching to another vector store would require rewriting `app/retrieval/qdrant.py` only — agents are isolated from the storage choice

## Rejected Alternatives

- **ChromaDB** — no sparse vector, no production-grade throughput, breaking API changes
- **Pinecone** — no self-hosted option, per-query cost, no sparse in same index
- **Weaviate** — heavier operational overhead, less clean Python client
- **pgvector** — no BM25 native, PostgreSQL not optimised for vector ANN at scale
