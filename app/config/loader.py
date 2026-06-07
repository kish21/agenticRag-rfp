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

# Norton Antivirus on this machine intercepts HTTPS via its own root CA.
# Patch requests.Session at class level so all instances (including LangSmith's
# internal background tracing thread) skip SSL verification for LangSmith domains.
if os.getenv("LANGSMITH_VERIFY_SSL", "true").lower() == "false":
    import requests as _req
    import urllib3 as _urllib3
    _urllib3.disable_warnings(_urllib3.exceptions.InsecureRequestWarning)
    _orig_req = _req.Session.request
    def _ls_no_ssl(self, method, url, **kwargs):
        if "langchain.com" in str(url) or "langsmith.com" in str(url):
            kwargs.setdefault("verify", False)
        return _orig_req(self, method, url, **kwargs)
    _req.Session.request = _ls_no_ssl

# BGE reranker (sentence-transformers) tries to reach huggingface.co on every
# startup to check for model updates. Norton blocks that HTTPS too.
# Set HF_HUB_OFFLINE=1 so it uses the local model cache without network checks.
if os.getenv("SSL_VERIFY", "true").lower() == "false":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")


# ─── Platform (engineering) shape ─────────────────────────────────────
class PlatformEmbedding(BaseModel):
    openai_model: str
    local_model: str
    dimensions: dict[str, int]   # model name -> vector size

class PlatformIngestion(BaseModel):
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    max_chunk_chars_for_rerank: int
    drops_root: str
    safe_id_pattern: str
    llm_attribution_confidence_floor: float = Field(ge=0.0, le=1.0)

class PlatformInjectionPattern(BaseModel):
    name: str
    regex: str

class PlatformInjectionDefence(BaseModel):
    # issue #133 — prompt-injection detection at ingestion. Defaulted so an older
    # platform.yaml without this block still loads. Note the absence-of-config
    # behaviour: with no `patterns`, scan_chunks is a no-op, so detection is
    # effectively DISABLED (the scan cannot fail-closed on rules it doesn't have).
    # When patterns ARE present, a match is fail-CLOSED (HARD block). The shipped
    # platform.yaml ships patterns, so the live default is detection-ON.
    enabled: bool = True
    block_threshold: int = Field(default=1, ge=1)
    patterns: list[PlatformInjectionPattern] = []

class PlatformSynthesisVerification(BaseModel):
    # P1.8 — second-pass verification of the Explanation Agent's FREE-TEXT prose
    # (executive_summary / compliance_narrative / scoring_narrative /
    # recommendation_rationale). The structured grounded_claims list is already
    # quote-verified upstream; the prose was not. A "second LLM call" fact-checks
    # each prose claim against the SAME retrieved evidence and the trusted
    # grounded_claims/system_facts. Defaulted so an older platform.yaml still
    # loads. enabled=True → grounding is core; one extra temperature-0 call/run.
    # The verified-claim ratio is gated like grounding_completeness:
    #   ratio < block_below → HARD (Critic blocks → existing retry loop regenerates)
    #   ratio < warn_below  → SOFT (flag for human review, no block)
    enabled: bool = True
    confidence_floor: float = Field(default=0.7, ge=0.0, le=1.0)
    block_below: float = Field(default=0.7, ge=0.0, le=1.0)
    warn_below: float = Field(default=0.9, ge=0.0, le=1.0)


class PlatformSelfConsistency(BaseModel):
    # P1.7 — self-consistency voting for BORDERLINE mandatory compliance checks.
    # Each check is normally one temperature-0 LLM call (deterministic). For a check
    # whose primary confidence falls in [confidence_min, confidence_max] the verdict is
    # fragile, so we resample the SAME decision `samples` times and take the majority.
    # Clear-cut checks (confidence outside the band) stay single-call → no added cost.
    # Defaulted so an older platform.yaml still loads. enabled=True is the owner decision.
    #   • Resamples MUST use temperature > 0 (diversity); at temp 0 the votes are identical
    #     and voting is a no-op. The first call stays temperature 0 (audit baseline).
    #   • No strict majority (e.g. a 1/1/1 three-way split) → fail-safe insufficient_evidence
    #     (owner decision; matches E3.b "can't confirm → insufficient").
    #   • An ODD `samples` is recommended so a 2-way split always resolves to a majority.
    enabled: bool = True
    samples: int = Field(default=3, ge=1)
    confidence_min: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_max: float = Field(default=0.75, ge=0.0, le=1.0)
    temperature: float = Field(default=0.5, ge=0.0, le=2.0)


class PlatformFewShot(BaseModel):
    # P1.9 (#60) — few-shot example bank for the Evaluation Agent. Past human
    # corrections (criterion/check level) are injected as calibration examples
    # into the evaluate-check / score-criterion prompts. Org-scoped: a tenant
    # only ever sees its OWN corrections (RLS on evaluation_corrections).
    #   • enabled=False  → no DB read, empty block, prompts byte-for-byte unchanged
    #     (this is why the benchmark org — which has no corrections — is unaffected).
    #   • max_examples   → ceiling on how many corrections are injected per item.
    #   • selection_strategy → "recent" (newest-first) is the only strategy today;
    #     the field exists so the policy is config-driven, not hardcoded.
    #   • min_reason_len → a correction with a thinner reason than this is skipped
    #     (a poor reason makes a poor example).
    #   • apply_to_checks / apply_to_scores → gate the two injection points
    #     independently. Critic still runs regardless — examples GUIDE, never bypass.
    enabled: bool = True
    max_examples: int = Field(default=3, ge=0)
    selection_strategy: str = "recent"
    min_reason_len: int = Field(default=20, ge=0)
    apply_to_checks: bool = True
    apply_to_scores: bool = True


class PlatformRetrieval(BaseModel):
    embedding_model: str
    embedding_dimensions: int
    candidate_count_before_rerank: int
    reranker_models: dict[str, str]    # provider -> model name
    dense_vector_name: str
    sparse_vector_name: str
    fusion_method: str
    rrf_k: int
    # issue #212 — confidence multiplier when the reranker fails and we fall back
    # to vector order (fail-open-but-loud). Defaulted so older configs still load.
    rerank_degraded_confidence_factor: float = 0.8

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
    generation_critic_max_retries: int
    task_duration_estimate_seconds: int

class PlatformGovernanceTier(BaseModel):
    tier: int
    approver_role: str
    max_value: float | None
    sla_hours: int

class PlatformGovernance(BaseModel):
    approval_tiers: list[PlatformGovernanceTier]
    recommendation_thresholds: dict[str, float]

class PlatformRanking(BaseModel):
    # E3.d — coverage floor below which a vendor's coverage-normalised score is
    # flagged 'low coverage — human review' rather than trusted at face value.
    min_coverage_for_trust: float = 0.5


class PlatformApiDocsTag(BaseModel):
    # DX-001 (#128) — one OpenAPI tag-group description. `name` MUST match a
    # router's `tags=[...]` value so Swagger/ReDoc attach the description.
    name: str
    description: str


class PlatformApiDocs(BaseModel):
    # DX-001 (#128) — public OpenAPI metadata surfaced at /docs, /redoc and
    # /openapi.json. PURE documentation; no runtime behaviour. Defaulted so an
    # older platform.yaml (without this block) still loads — with empty values
    # main.py simply omits the corresponding OpenAPI fields.
    description: str = ""
    contact_name: str = ""
    contact_email: str = ""
    contact_url: str = ""
    license_name: str = ""
    license_url: str = ""
    tags: list[PlatformApiDocsTag] = []

class PlatformConfig(BaseModel):
    embedding: PlatformEmbedding
    ingestion: PlatformIngestion
    injection_defence: PlatformInjectionDefence = PlatformInjectionDefence()
    synthesis_verification: PlatformSynthesisVerification = PlatformSynthesisVerification()
    self_consistency: PlatformSelfConsistency = PlatformSelfConsistency()
    few_shot: PlatformFewShot = PlatformFewShot()
    retrieval: PlatformRetrieval
    llm: PlatformLLM
    infrastructure: PlatformInfra
    governance: PlatformGovernance
    ranking: PlatformRanking = PlatformRanking()
    api_docs: PlatformApiDocs = PlatformApiDocs()
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

class ProductRFPDefaults(BaseModel):
    """Phase 5 RFP lifecycle defaults — see app/api/rfp_routes.py."""
    default_deadline_days: int = Field(ge=1, le=365)
    default_autonomy_mode: str
    allowed_autonomy_modes: list[str]
    write_roles: list[str]


class ProductRBAC(BaseModel):
    """RBAC tunables — #55. Which JWT roles may read the org-wide audit trail
    (GET /api/v1/audit/*). Defaulted so a product.yaml without an `rbac:` block
    still loads (auditor is the compliance persona; admins included by default)."""
    audit_read_roles: list[str] = ["auditor", "company_admin", "platform_admin"]


class ProductGDPR(BaseModel):
    """GDPR data-subject rights — Mode B tenant erasure (issue #119).

    Defaulted so a product.yaml without a `gdpr:` block still loads.
    """
    keep_erasure_receipt: bool = True
    block_if_runs_in_flight: bool = True


class ProductConfig(BaseModel):
    new_org_defaults: dict      # see OrgSettings model for keys
    presets: dict[str, Preset]
    score_bands: ProductScoreBands
    audit: ProductAudit
    rfp_defaults: ProductRFPDefaults
    gdpr: ProductGDPR = ProductGDPR()
    rbac: ProductRBAC = ProductRBAC()


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
    # Modal environment the agentic-platform app is deployed to (its secret lives
    # in "rag"). Runtime Function.from_name lookups must target this env, else they
    # default to "main" and raise "App ... not found in environment 'main'".
    modal_environment: str = "rag"

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
    allowed_origins: list[str] = ["http://localhost:3000"]
    # Deployment environment. Drives security defaults (e.g. secure cookies).
    # Set ENVIRONMENT=production (or staging) on any non-local deploy.
    environment: str = "development"
    # Whether to mark the auth cookie Secure (HTTPS-only). Defaults to True in
    # production/staging; can be forced via COOKIE_SECURE for edge cases
    # (e.g. local HTTPS, or a prod proxy that terminates TLS upstream).
    cookie_secure: bool = False

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
    # Dedicated NON-SUPERUSER, non-owner application role. RLS only governs a
    # role that is neither the table owner nor a superuser/BYPASSRLS role, so
    # runtime queries MUST connect as this role for tenant isolation to bite.
    # The owner role above (postgres_user) is used only for DDL/migrations,
    # identity/auth lookups, and cross-org system jobs. See app/db/session.py
    # and docs/dev/BACKLOG.md P0.16.
    postgres_app_user: str = "platform_app"
    postgres_app_password: str = ""

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
    rate_metrics_enabled: bool = False   # persist per-minute rate stats for the cross-process monitor
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

    _env = _e("ENVIRONMENT", "development")

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
        "modal_environment":          _e("MODAL_ENVIRONMENT", "rag"),
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
        "allowed_origins":            [o.strip() for o in _e("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
        "environment":                _env,
        "cookie_secure":              _eb("COOKIE_SECURE", _env.lower() in ("production", "prod", "staging", "stage")),
        "qdrant_host":                _e("QDRANT_HOST", "localhost"),
        "qdrant_port":                _ei("QDRANT_PORT", 6333),
        "qdrant_collection_prefix":   _e("QDRANT_COLLECTION_PREFIX", "platform"),
        "postgres_host":              _e("POSTGRES_HOST", "localhost"),
        "postgres_port":              _ei("POSTGRES_PORT", 5432),
        "postgres_db":                _e("POSTGRES_DB", "agenticplatform"),
        "postgres_user":              _e("POSTGRES_USER", "platformuser"),
        "postgres_password":          _e("POSTGRES_PASSWORD"),
        "postgres_app_user":          _e("POSTGRES_APP_USER", "platform_app"),
        "postgres_app_password":      _e("POSTGRES_APP_PASSWORD"),
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
        "rate_metrics_enabled":       _eb("RATE_METRICS_ENABLED", False),
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
