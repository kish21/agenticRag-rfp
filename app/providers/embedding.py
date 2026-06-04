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

# OpenAI / Azure embeddings cap a single request at 2048 input items (and ~300k
# tokens). A large RFP can produce more chunks than that, so the API providers
# must sub-batch or the whole ingestion fails with a 400. 256 keeps each request
# well under both the item and token ceilings.
_API_EMBED_BATCH_SIZE = 256


def _chunked(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


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
    vectors: list[list[float]] = []
    for batch in _chunked(texts, _API_EMBED_BATCH_SIZE):
        response = client.embeddings.create(model=model, input=[t[:8000] for t in batch])
        vectors.extend(item.embedding for item in response.data)
    return vectors


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
    deployment = settings.azure_openai_embedding_deployment
    vectors: list[list[float]] = []
    for batch in _chunked(texts, _API_EMBED_BATCH_SIZE):
        response = client.embeddings.create(model=deployment, input=[t[:8000] for t in batch])
        vectors.extend(item.embedding for item in response.data)
    return vectors


# ── Local sentence-transformers backend (CPU) ─────────────────────────────────

def _get_local_model():
    global _local_model
    if _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            # sentence-transformers (+ transformers/torch) is in the OPTIONAL
            # requirements-local.txt, not the prod image. Selecting EMBEDDING_PROVIDER=local
            # without it is a configuration error — fail loudly. Default deployments use
            # EMBEDDING_PROVIDER=openai (or =modal) and never reach here.
            raise RuntimeError(
                "EMBEDDING_PROVIDER=local requires the 'sentence-transformers' package, "
                "which is not installed. Either install it "
                "(pip install -r requirements-local.txt) or use EMBEDDING_PROVIDER=openai "
                "or =modal."
            ) from e
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
