"""
Loads .env + platform.yaml + product.yaml into a typed Settings object.
Fails fast on missing required values, with a clear pointer to which
file should contain the value.

The Settings object is the single import point for all configuration.
Secrets/infra fields come from .env; platform/product fields from YAMLs.
"""
import os
from pathlib import Path
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

CONFIG_DIR = Path(__file__).parent
# Load .env from repo root so all env vars are available
load_dotenv(CONFIG_DIR.parent.parent / ".env", override=False)


# ─── Platform (engineering) shape ─────────────────────────────────────
class PlatformEmbedding(BaseModel):
    openai_model: str
    local_model: str
    dimensions: dict[str, int]   # model name -> vector size

class PlatformIngestion(BaseModel):
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    max_chunk_chars_for_rerank: int

class PlatformRetrieval(BaseModel):
    embedding_model: str
    embedding_dimensions: int
    candidate_count_before_rerank: int
    reranker_models: dict[str, str]    # provider -> model name
    dense_vector_name: str
    sparse_vector_name: str
    fusion_method: str
    rrf_k: int

class PlatformLLM(BaseModel):
    primary_model: str
    fallback_model: str
    compression_model: str
    max_tokens: int
    request_timeout_seconds: int

class PlatformInfra(BaseModel):
    org_settings_cache_ttl_seconds: int
    max_retries: int
    qdrant_collection_pattern: str
    retrieval_critic_max_retries: int
    retrieval_critic_confidence_floor: float
    extraction_critic_max_retries: int
    extraction_critic_confidence_floor: float

class PlatformConfig(BaseModel):
    embedding: PlatformEmbedding
    ingestion: PlatformIngestion
    retrieval: PlatformRetrieval
    llm: PlatformLLM
    infrastructure: PlatformInfra
    hyde_templates: dict[str, str]    # doc_type -> template
    retrieval_critic_prompt: str
    extraction_critic_prompt: str


# ─── Product (business) shape ─────────────────────────────────────────
class Preset(BaseModel):
    label: str
    summary: str
    cost_multiplier: float
    config: dict    # validated at use-site against OrgSettings fields

class ProductScoreBands(BaseModel):
    strongly_recommended: int = Field(ge=0, le=100)
    recommended: int = Field(ge=0, le=100)
    acceptable: int = Field(ge=0, le=100)
    marginal: int = Field(ge=0, le=100)

class ProductAudit(BaseModel):
    retain_decisions_years: int = Field(ge=1, le=50)
    require_human_signoff: bool
    citation_required: bool

class ProductConfig(BaseModel):
    new_org_defaults: dict      # see OrgSettings model for keys
    presets: dict[str, Preset]
    score_bands: ProductScoreBands
    audit: ProductAudit


# ─── Unified Settings (env secrets + YAML tunables) ───────────────────
class Settings(BaseModel):
    # ── LLM provider selector (from .env) ─────────────────────────────
    llm_provider: str = "openai"

    # ── OpenAI ────────────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"                       # legacy shim — prefer platform.llm.primary_model
    openai_embedding_model: str = "text-embedding-3-large"  # legacy shim — prefer platform.retrieval.embedding_model
    openai_temperature: float = 0.1

    # ── Azure OpenAI ──────────────────────────────────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"
    azure_openai_api_version: str = "2024-12-01-preview"

    # ── Anthropic ─────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # ── OpenRouter ────────────────────────────────────────────────────
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o"

    # ── Ollama ────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:72b"

    # ── Modal LLM (vLLM serving Qwen 2.5 72B on A100-80GB) ───────────
    modal_llm_endpoint: str = ""
    modal_llm_model: str = "qwen2.5-72b"

    # ── LangSmith ─────────────────────────────────────────────────────
    langsmith_tracing: bool = True
    langsmith_api_key: str = ""
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "agentic-platform-dev"

    # ── LangFuse ──────────────────────────────────────────────────────
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # ── Embedding provider ────────────────────────────────────────────
    # Options: openai | azure | local | modal
    # openai / azure → OpenAI / Azure OpenAI embedding API
    # local          → sentence-transformers on FastAPI server (CPU)
    # modal          → sentence-transformers on Modal GPU (open source)
    embedding_provider: str = "openai"
    embedding_model_local: str = "BAAI/bge-large-en-v1.5"

    # ── Observability provider ────────────────────────────────────────
    # Options: langfuse | stdout | none
    observability_provider: str = "langfuse"

    # ── Reranker ──────────────────────────────────────────────────────
    reranker_provider: str = "bge"
    cohere_api_key: str = ""
    cohere_rerank_model: str = "rerank-english-v3.0"   # legacy shim — prefer platform.retrieval.reranker_models['cohere']

    # ── App ───────────────────────────────────────────────────────────
    app_api_key: str = ""

    # ── Qdrant ────────────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_prefix: str = "platform"

    # ── Postgres ──────────────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "agenticplatform"
    postgres_user: str = "platformuser"
    postgres_password: str = ""

    # ── Auth ──────────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 480

    # ── Dev user ──────────────────────────────────────────────────────
    dev_user_email: str = "dev@platform.local"
    dev_user_password: str = "devpassword2026"
    dev_org_id: str = "00000000-0000-0000-0000-000000000001"
    dev_user_role: str = "company_admin"

    # ── Slack ─────────────────────────────────────────────────────────
    slack_bot_token: str = ""
    slack_channel_id: str = ""

    # ── Compute ───────────────────────────────────────────────────────
    compute_provider: str = "modal"
    modal_token_id: str = ""
    modal_token_secret: str = ""

    # ── Platform behaviour ────────────────────────────────────────────
    confidence_threshold: float = 0.75   # legacy shim — prefer product.yaml preset configs
    max_retry_limit: int = 5             # legacy shim — prefer platform.infrastructure.max_retries
    hard_flag_blocks_pipeline: bool = True
    rate_limit_requests_per_minute: int = 50
    skip_embeddings: bool = False
    ssl_verify: bool = True

    # ── YAML-sourced (platform engineering + product business) ─────────
    platform: PlatformConfig
    product:  ProductConfig


def _e(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _ei(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _ef(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _eb(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"CONFIG ERROR: missing required file {path}\n"
            f"Create it (this is a project-owned source file, not a secret)."
        )
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_settings() -> Settings:
    platform_raw = _load_yaml(CONFIG_DIR / "platform.yaml")
    product_raw  = _load_yaml(CONFIG_DIR / "product.yaml")

    env: dict = {
        "llm_provider":               _e("LLM_PROVIDER", "openai"),
        "openai_api_key":             _e("OPENAI_API_KEY"),
        "openai_model":               _e("OPENAI_MODEL", "gpt-4o"),
        "openai_embedding_model":     _e("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
        "openai_temperature":         _ef("OPENAI_TEMPERATURE", 0.1),
        "azure_openai_endpoint":      _e("AZURE_OPENAI_ENDPOINT"),
        "azure_openai_api_key":       _e("AZURE_OPENAI_API_KEY"),
        "azure_openai_deployment":    _e("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        "azure_openai_embedding_deployment": _e("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"),
        "azure_openai_api_version":   _e("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        "anthropic_api_key":          _e("ANTHROPIC_API_KEY"),
        "anthropic_model":            _e("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        "openrouter_api_key":         _e("OPENROUTER_API_KEY"),
        "openrouter_base_url":        _e("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        "openrouter_model":           _e("OPENROUTER_MODEL", "openai/gpt-4o"),
        "ollama_base_url":            _e("OLLAMA_BASE_URL", "http://localhost:11434"),
        "ollama_model":               _e("OLLAMA_MODEL", "qwen2.5:72b"),
        "modal_llm_endpoint":         _e("MODAL_LLM_ENDPOINT", ""),
        "modal_llm_model":            _e("MODAL_LLM_MODEL", "qwen2.5-72b"),
        "langsmith_tracing":          _eb("LANGSMITH_TRACING", True),
        "langsmith_api_key":          _e("LANGSMITH_API_KEY"),
        "langsmith_endpoint":         _e("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        "langsmith_project":          _e("LANGSMITH_PROJECT", "agentic-platform-dev"),
        "langfuse_public_key":        _e("LANGFUSE_PUBLIC_KEY"),
        "langfuse_secret_key":        _e("LANGFUSE_SECRET_KEY"),
        "langfuse_host":              _e("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        "embedding_provider":         _e("EMBEDDING_PROVIDER", "openai"),
        "embedding_model_local":      _e("EMBEDDING_MODEL_LOCAL", "BAAI/bge-large-en-v1.5"),
        "observability_provider":     _e("OBSERVABILITY_PROVIDER", "langfuse"),
        "reranker_provider":          _e("RERANKER_PROVIDER", "bge"),
        "cohere_api_key":             _e("COHERE_API_KEY"),
        "cohere_rerank_model":        _e("COHERE_RERANK_MODEL", "rerank-english-v3.0"),
        "app_api_key":                _e("APP_API_KEY"),
        "qdrant_host":                _e("QDRANT_HOST", "localhost"),
        "qdrant_port":                _ei("QDRANT_PORT", 6333),
        "qdrant_collection_prefix":   _e("QDRANT_COLLECTION_PREFIX", "platform"),
        "postgres_host":              _e("POSTGRES_HOST", "localhost"),
        "postgres_port":              _ei("POSTGRES_PORT", 5432),
        "postgres_db":                _e("POSTGRES_DB", "agenticplatform"),
        "postgres_user":              _e("POSTGRES_USER", "platformuser"),
        "postgres_password":          _e("POSTGRES_PASSWORD"),
        "jwt_secret_key":             _e("JWT_SECRET_KEY", "change-me-in-production"),
        "jwt_algorithm":              _e("JWT_ALGORITHM", "HS256"),
        "jwt_expiry_minutes":         _ei("JWT_EXPIRY_MINUTES", 480),
        "dev_user_email":             _e("DEV_USER_EMAIL", "dev@platform.local"),
        "dev_user_password":          _e("DEV_USER_PASSWORD", "devpassword2026"),
        "dev_org_id":                 _e("DEV_ORG_ID", "00000000-0000-0000-0000-000000000001"),
        "dev_user_role":              _e("DEV_USER_ROLE", "company_admin"),
        "slack_bot_token":            _e("SLACK_BOT_TOKEN"),
        "slack_channel_id":           _e("SLACK_CHANNEL_ID"),
        "compute_provider":           _e("COMPUTE_PROVIDER", "modal"),
        "modal_token_id":             _e("MODAL_TOKEN_ID"),
        "modal_token_secret":         _e("MODAL_TOKEN_SECRET"),
        "confidence_threshold":       _ef("CONFIDENCE_THRESHOLD", 0.75),
        "max_retry_limit":            _ei("MAX_RETRY_LIMIT", 5),
        "hard_flag_blocks_pipeline":  _eb("HARD_FLAG_BLOCKS_PIPELINE", True),
        "rate_limit_requests_per_minute": _ei("RATE_LIMIT_REQUESTS_PER_MINUTE", 50),
        "skip_embeddings":            _eb("SKIP_EMBEDDINGS", False),
        "ssl_verify":                 _eb("SSL_VERIFY", True),
    }

    try:
        return Settings(
            **env,
            platform=PlatformConfig(**platform_raw),
            product=ProductConfig(**product_raw),
        )
    except ValidationError as e:
        raise SystemExit(
            "CONFIG VALIDATION FAILED.\n"
            "Check the file that owns each missing field:\n"
            "  - platform.*  -> app/config/platform.yaml\n"
            "  - product.*   -> app/config/product.yaml\n"
            "  - secrets     -> .env\n\n"
            f"{e}"
        )


settings = load_settings()
