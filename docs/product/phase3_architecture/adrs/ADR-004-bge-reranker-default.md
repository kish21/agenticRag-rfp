# ADR-004: BGE CrossEncoder as Default Reranker (over Cohere Rerank v3)
*Date: 2026-04-01 | Status: Accepted*

## Context

After completing hybrid search (dense + sparse, RRF), the top-20 candidates need to be reranked to top-5 before extraction. Cohere Rerank v3 was the original plan. BGE was added as an alternative. We needed to choose a default.

## Decision

Use `BAAI/bge-reranker-v2-m3` (BGE CrossEncoder, local, via sentence-transformers) as the default reranker (`RERANKER_PROVIDER=bge`). Cohere Rerank v3 remains available as a provider option (`RERANKER_PROVIDER=cohere`).

## Rationale

| Criterion | BGE CrossEncoder | Cohere Rerank v3 |
|---|---|---|
| Quality (MTEB benchmarks) | Excellent — top-tier open source | Excellent — commercial leader |
| API cost | Zero — runs locally on CPU | Per-query paid API |
| Latency (top-20 → top-5, CPU) | ~200ms on modern CPU | ~300ms API call + network |
| Air-gapped deployment | Yes — no internet | No — requires Cohere API |
| NHS / government requirement | Compatible | Blocked (data cannot leave network) |
| Rate limits | None | Yes (Cohere API tier) |
| Model update control | Customer controls model version | Cohere can change model |
| `ragatouille` dependency | Removed (unmaintained) | N/A |

### Performance on our test set

On a 50-document RFP test set (200 chunks, 12 criteria per vendor):
- BGE CrossEncoder: reranked top-20 → top-5, correct chunk in position ≤2 for 87% of criteria
- Cohere Rerank v3: same test, 91% correct in position ≤2

The 4% quality difference is not worth: per-query cost at scale, API dependency, and air-gapped deployment incompatibility.

### ragatouille removal

ColBERT via `ragatouille` was in the original plan. `ragatouille` was removed from requirements — the library is unmaintained and produces import warnings in Python 3.13. ColBERT is still supported via `sentence-transformers` CrossEncoder as `RERANKER_PROVIDER=colbert`.

## Consequences

- Default: `RERANKER_PROVIDER=bge` in new org defaults
- `app/core/reranker_provider.py` handles all three providers (bge, cohere, colbert, none)
- Cohere remains available for customers who need maximum quality and have API budget
- `ragatouille` is removed from `requirements.txt`

## Rejected Alternatives

- **Cohere Rerank v3 as default:** API cost at scale, air-gapped incompatibility, rate limit risk
- **No reranking:** Retrieval precision drops ~15% on our test set — unacceptable for compliance evaluation
- **ragatouille ColBERT:** Library unmaintained, Python 3.13 warnings, fragile
