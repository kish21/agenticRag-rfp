"""
Embedding provider abstraction.
Mirrors llm_provider.py pattern — swap backends via EMBEDDING_PROVIDER in .env.

Supported providers:
  openai  — OpenAI text-embedding-3-large (default, 3072-dim)
  azure   — Azure OpenAI embedding deployment (3072-dim)
  local   — sentence-transformers on FastAPI server CPU (1024-dim for bge-large)
  modal   — sentence-transformers on Modal A10G GPU (1024-dim, batch-optimised)

Switching models changes vector dimensions. Existing Qdrant collections must be
re-ingested if EMBEDDING_PROVIDER changes (dimensions are incompatible).
New collections are created at the correct dimension automatically.
"""
from app.config import settings

_local_model = None


def _get_active_model_name() -> str:
    provider = settings.embedding_provider.lower()
    if provider in ("openai", "azure"):
        if provider == "azure":
            return settings.azure_openai_embedding_deployment
        return settings.platform.embedding.openai_model
    return settings.embedding_model_local


def get_embedding_dimensions() -> int:
    """Returns the vector size for the active embedding model."""
    model = _get_active_model_name()
    dims = settings.platform.embedding.dimensions
    return dims.get(model, 3072)


def embed_text(text: str) -> list[float]:
    """Embed a single text — used for retrieval queries."""
    if settings.skip_embeddings:
        return [0.0] * get_embedding_dimensions()

    provider = settings.embedding_provider.lower()

    if provider == "openai":
        return _embed_openai([text])[0]
    elif provider == "azure":
        return _embed_azure([text])[0]
    elif provider in ("local", "modal"):
        # For single texts, local CPU is fast enough — avoids Modal cold start
        return _embed_local([text])[0]
    else:
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER: '{provider}'. "
            f"Valid options: openai, azure, local, modal"
        )


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts — used for ingestion chunks."""
    if not texts:
        return []
    if settings.skip_embeddings:
        dim = get_embedding_dimensions()
        return [[0.0] * dim for _ in texts]

    provider = settings.embedding_provider.lower()

    if provider == "openai":
        return _embed_openai(texts)
    elif provider == "azure":
        return _embed_azure(texts)
    elif provider == "local":
        return _embed_local(texts)
    elif provider == "modal":
        return _embed_modal_batch(texts)
    else:
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER: '{provider}'. "
            f"Valid options: openai, azure, local, modal"
        )


# ── OpenAI backend ────────────────────────────────────────────────────────────

def _embed_openai(texts: list[str]) -> list[list[float]]:
    import httpx
    from openai import OpenAI
    http_client = httpx.Client(verify=False) if not settings.ssl_verify else None
    kwargs = {"api_key": settings.openai_api_key}
    if http_client:
        kwargs["http_client"] = http_client
    client = OpenAI(**kwargs)
    model = settings.platform.embedding.openai_model
    response = client.embeddings.create(model=model, input=[t[:8000] for t in texts])
    return [item.embedding for item in response.data]


# ── Azure OpenAI backend ──────────────────────────────────────────────────────

def _embed_azure(texts: list[str]) -> list[list[float]]:
    import httpx
    from openai import AzureOpenAI
    http_client = httpx.Client(verify=False) if not settings.ssl_verify else None
    kwargs = {
        "api_key": settings.azure_openai_api_key,
        "azure_endpoint": settings.azure_openai_endpoint,
        "api_version": settings.azure_openai_api_version,
    }
    if http_client:
        kwargs["http_client"] = http_client
    client = AzureOpenAI(**kwargs)
    response = client.embeddings.create(
        model=settings.azure_openai_embedding_deployment,
        input=[t[:8000] for t in texts],
    )
    return [item.embedding for item in response.data]


# ── Local sentence-transformers backend (CPU) ─────────────────────────────────

def _get_local_model():
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer
        _local_model = SentenceTransformer(
            settings.embedding_model_local,
            trust_remote_code=True,
        )
    return _local_model


def _embed_local(texts: list[str]) -> list[list[float]]:
    model = _get_local_model()
    embeddings = model.encode(
        [t[:8000] for t in texts],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embeddings.tolist()


# ── Modal GPU backend (batch ingestion) ───────────────────────────────────────

def _embed_modal_batch(texts: list[str]) -> list[list[float]]:
    try:
        import modal
        fn = modal.Function.from_name("agentic-platform", "embed_batch_on_modal")
        return fn.remote(texts, settings.embedding_model_local)
    except Exception as e:
        print(f"[embedding] Modal batch embed failed: {e}. Falling back to local.")
        return _embed_local(texts)
