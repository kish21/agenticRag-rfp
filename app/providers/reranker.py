"""
Reranker provider abstraction.
Mirrors llm_provider.py pattern exactly.
Switch reranker by changing RERANKER_PROVIDER in .env.
No agent code changes required.

Providers:
  bge     — BGE CrossEncoder via sentence-transformers on the local box (needs
            the model in the local HF cache; first run downloads ~2.3GB from
            HuggingFace).
  modal   — the SAME open-source BGE CrossEncoder, but run on a Modal A10G GPU
            (deploy/modal_app.py::rerank_on_modal). Dev and production both call
            this one deployed model, so scores are identical across environments
            and the local box never needs to reach HuggingFace. Requires the Modal
            app to be deployed (`modal deploy deploy/modal_app.py`); falls back to
            vector order if Modal is unreachable.
  cohere  — managed Cohere Rerank API (not open source).
  colbert — ColBERT via ragatouille (unmaintained; opt-in).
  none    — no rerank; vector-score order.
"""
import logging

from app.config import settings

logger = logging.getLogger(__name__)

_bge_model = None
_colbert_model = None


def _get_bge_model():
    global _bge_model
    if _bge_model is None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:
            # sentence-transformers (+ transformers/torch) lives in the OPTIONAL
            # requirements-local.txt, not the prod image. Selecting the LOCAL bge
            # backend without it is a configuration error — fail loudly rather than
            # silently downgrading to no-rerank. Default deployments use
            # RERANKER_PROVIDER=modal (BGE on Modal) and never reach here.
            raise RuntimeError(
                "RERANKER_PROVIDER=bge (local) requires the 'sentence-transformers' "
                "package, which is not installed. Either install it "
                "(pip install -r requirements-local.txt) or use RERANKER_PROVIDER=modal "
                "(BGE on Modal, no local ML deps) or =cohere."
            ) from e
        _bge_model = CrossEncoder(
            settings.platform.retrieval.reranker_models["bge"],
            max_length=settings.platform.ingestion.max_chunk_chars_for_rerank
        )
    return _bge_model


def _get_colbert_model():
    global _colbert_model
    if _colbert_model is None:
        try:
            from ragatouille import RAGPretrainedModel
        except ImportError as e:
            # ragatouille was removed from requirements (unmaintained). Selecting
            # RERANKER_PROVIDER=colbert is therefore a configuration error — fail
            # loudly here rather than silently downgrading to no-rerank, which
            # would degrade retrieval quality with no operator signal.
            raise RuntimeError(
                "RERANKER_PROVIDER=colbert requires the 'ragatouille' package, "
                "which is not installed (removed from requirements as unmaintained). "
                "Use RERANKER_PROVIDER=bge or =cohere, or reinstall ragatouille."
            ) from e
        _colbert_model = RAGPretrainedModel.from_pretrained(
            settings.platform.retrieval.reranker_models["colbert"]
        )
    return _colbert_model


def rerank(
    query: str,
    candidates: list[dict],
    top_n: int = 5,
    provider: str | None = None,
    warnings: list[str] | None = None,
) -> list[dict]:
    """
    Reranks candidates using the configured provider.
    All providers return candidates with rerank_score added.
    Falls back to vector score order if provider fails.

    candidates: list of dicts with 'text' and 'score' keys
    provider: override global RERANKER_PROVIDER (e.g. from org_settings)
    warnings: optional mutable list. When a NON-'none' provider fails or is
              unknown and we fail-open to vector-score order, an operator-facing
              degradation message is appended so the caller can surface it
              (fail-open but LOUD — air-gapped boxes silently degrading is the
              exact failure #212 addresses). 'none' is an intentional choice and
              is never reported as degraded.
    returns: top_n candidates sorted by rerank_score descending
    """
    if not candidates:
        return candidates

    provider = (provider or settings.reranker_provider).lower()

    def _degraded(detail: str) -> list[dict]:
        if warnings is not None and provider != "none":
            warnings.append(
                f"Reranking degraded: provider '{provider}' {detail}; "
                f"results fell back to vector-score order."
            )
        return _rerank_none(candidates, top_n)

    try:
        if provider == "cohere":
            return _rerank_cohere(query, candidates, top_n)
        elif provider == "bge":
            return _rerank_bge(query, candidates, top_n)
        elif provider == "modal":
            return _rerank_modal(query, candidates, top_n)
        elif provider == "colbert":
            return _rerank_colbert(query, candidates, top_n)
        elif provider == "none":
            return _rerank_none(candidates, top_n)
        else:
            logger.warning("Unknown reranker provider %r — falling back to no-rerank.", provider)
            return _degraded("is not a recognised reranker")
    except Exception as e:
        # Surface via the structured logger (not print) so a misconfigured or
        # broken reranker fail-open to vector-score order is visible to operators.
        logger.warning(
            "Reranker %r failed (%s) — falling back to vector-score order.",
            provider, e,
        )
        return _degraded(f"is unavailable ({e})")


def _rerank_cohere(
    query: str,
    candidates: list[dict],
    top_n: int
) -> list[dict]:
    import cohere
    co = cohere.ClientV2(api_key=settings.cohere_api_key)
    _max_chars = settings.platform.ingestion.max_chunk_chars_for_rerank
    docs = [c["text"][:_max_chars] for c in candidates]
    results = co.rerank(
        model=settings.platform.retrieval.reranker_models["cohere"],
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
    _max_chars = settings.platform.ingestion.max_chunk_chars_for_rerank
    pairs = [(query, c["text"][:_max_chars]) for c in candidates]
    scores = model.predict(pairs)
    for i, score in enumerate(scores):
        candidates[i]["rerank_score"] = float(score)
    reranked = sorted(
        candidates,
        key=lambda x: x["rerank_score"],
        reverse=True
    )
    return reranked[:top_n]


def _rerank_modal(
    query: str,
    candidates: list[dict],
    top_n: int
) -> list[dict]:
    """Rerank via the BGE CrossEncoder deployed on Modal (RERANKER_PROVIDER=modal).

    Only the per-pair scoring runs on the Modal GPU; the sort + top-N is done here
    so the ranking is identical to the local `bge` path. Uses the same BGE model
    name as `bge`, guaranteeing dev/prod parity. If Modal is unreachable, the
    exception propagates to rerank()'s handler, which falls back to vector order.
    """
    import modal
    _max_chars = settings.platform.ingestion.max_chunk_chars_for_rerank
    docs = [c["text"][:_max_chars] for c in candidates]
    model_name = settings.platform.retrieval.reranker_models["bge"]
    fn = modal.Function.from_name(
        "agentic-platform", "rerank_on_modal",
        environment_name=settings.modal_environment,
    )
    scores = fn.remote(query, docs, model_name)
    for i, score in enumerate(scores):
        candidates[i]["rerank_score"] = float(score)
    return sorted(
        candidates,
        key=lambda x: x["rerank_score"],
        reverse=True
    )[:top_n]


def _rerank_colbert(
    query: str,
    candidates: list[dict],
    top_n: int
) -> list[dict]:
    model = _get_colbert_model()
    _max_chars = settings.platform.ingestion.max_chunk_chars_for_rerank
    docs = [c["text"][:_max_chars] for c in candidates]
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
