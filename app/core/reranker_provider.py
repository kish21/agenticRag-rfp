"""
Reranker provider abstraction.
Mirrors llm_provider.py pattern exactly.
Switch reranker by changing RERANKER_PROVIDER in .env.
No agent code changes required.
"""
from app.config import settings

_bge_model = None
_colbert_model = None


def _get_bge_model():
    global _bge_model
    if _bge_model is None:
        from sentence_transformers import CrossEncoder
        _bge_model = CrossEncoder(
            "BAAI/bge-reranker-v2-m3",
            max_length=512
        )
    return _bge_model


def _get_colbert_model():
    global _colbert_model
    if _colbert_model is None:
        from ragatouille import RAGPretrainedModel
        _colbert_model = RAGPretrainedModel.from_pretrained(
            "colbert-ir/colbertv2.0"
        )
    return _colbert_model


def rerank(
    query: str,
    candidates: list[dict],
    top_n: int = 5
) -> list[dict]:
    """
    Reranks candidates using the configured provider.
    All providers return candidates with rerank_score added.
    Falls back to vector score order if provider fails.

    candidates: list of dicts with 'text' and 'score' keys
    returns: top_n candidates sorted by rerank_score descending
    """
    if not candidates:
        return candidates

    provider = settings.reranker_provider.lower()

    try:
        if provider == "cohere":
            return _rerank_cohere(query, candidates, top_n)
        elif provider == "bge":
            return _rerank_bge(query, candidates, top_n)
        elif provider == "colbert":
            return _rerank_colbert(query, candidates, top_n)
        elif provider == "none":
            return _rerank_none(candidates, top_n)
        else:
            print(f"Unknown reranker provider: {provider}. Using none.")
            return _rerank_none(candidates, top_n)
    except Exception as e:
        print(f"Reranker {provider} failed: {e}. Falling back to vector score.")
        return _rerank_none(candidates, top_n)


def _rerank_cohere(
    query: str,
    candidates: list[dict],
    top_n: int
) -> list[dict]:
    import cohere
    co = cohere.ClientV2(api_key=settings.cohere_api_key)
    docs = [c["text"][:512] for c in candidates]
    results = co.rerank(
        model=settings.cohere_rerank_model,
        query=query,
        documents=docs,
        top_n=top_n,
    )
    reranked = []
    for r in results.results:
        candidate = candidates[r.index].copy()
        candidate["rerank_score"] = r.relevance_score
        reranked.append(candidate)
    return reranked


def _rerank_bge(
    query: str,
    candidates: list[dict],
    top_n: int
) -> list[dict]:
    model = _get_bge_model()
    pairs = [(query, c["text"][:512]) for c in candidates]
    scores = model.predict(pairs)
    for i, score in enumerate(scores):
        candidates[i]["rerank_score"] = float(score)
    reranked = sorted(
        candidates,
        key=lambda x: x["rerank_score"],
        reverse=True
    )
    return reranked[:top_n]


def _rerank_colbert(
    query: str,
    candidates: list[dict],
    top_n: int
) -> list[dict]:
    model = _get_colbert_model()
    docs = [c["text"][:512] for c in candidates]
    results = model.rerank(query, docs, k=top_n)
    reranked = []
    for r in results:
        idx = r["result_index"]
        candidate = candidates[idx].copy()
        candidate["rerank_score"] = r["score"]
        reranked.append(candidate)
    return reranked


def _rerank_none(
    candidates: list[dict],
    top_n: int
) -> list[dict]:
    """No reranking — return top_n by vector score."""
    for c in candidates:
        c["rerank_score"] = c.get("score", 0.0)
    return sorted(
        candidates,
        key=lambda x: x["rerank_score"],
        reverse=True
    )[:top_n]
