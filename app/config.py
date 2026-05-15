from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── LLM Provider ─────────────────────────────────────
    # Change llm_provider to swap the model — no engine code changes required.
    # Supported: openai | anthropic | openrouter | ollama
    llm_provider: str = "openai"

    # OpenAI (also used for embeddings regardless of llm_provider)
    openai_api_key: str = ""
    openai_temperature: float = 0.1

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-12-01-preview"

    # Anthropic
    anthropic_api_key: str = ""

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Ollama (local — Qwen, Llama, Mistral etc.)
    ollama_base_url: str = "http://localhost:11434"

    # LangSmith (new SDK uses LANGSMITH_* prefix — v0.2+)
    langsmith_tracing: bool = True
    langsmith_api_key: str = ""
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "agentic-platform-dev"

    # LangFuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Observability provider
    # Options: langfuse | stdout | none
    # langfuse — LangFuse cloud (default)
    # stdout   — JSON logs to console (dev / air-gapped)
    # none     — silent drop (testing, CI)
    observability_provider: str = "langfuse"

    # Reranker provider
    # Options: cohere | bge | colbert | none
    # cohere  — Cohere Rerank API (paid, best quality)
    # bge     — BAAI/bge-reranker-v2-m3 (local, no API key)
    # colbert — colbert-ir/colbertv2.0 via sentence-transformers CrossEncoder (local)
    # none    — fall back to vector score order (no reranking)
    reranker_provider: str = "bge"

    # Cohere
    cohere_api_key: str = ""

    # App
    app_api_key: str = ""

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_prefix: str = "platform"

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "agenticplatform"
    postgres_user: str = "platformuser"
    postgres_password: str = ""

    # Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 480  # 8 hours

    # Default dev user (never use in production)
    dev_user_email: str = "dev@platform.local"
    dev_user_password: str = "devpassword2026"
    dev_org_id: str = "00000000-0000-0000-0000-000000000001"
    dev_user_role: str = "company_admin"

    # Slack
    slack_bot_token: str = ""
    slack_channel_id: str = ""

    # Compute provider for burst jobs and scheduled tasks
    # Supported: modal | aws_lambda | azure_functions | gcp_cloudrun | local_worker
    compute_provider: str = "modal"

    # Modal credentials (used when compute_provider=modal)
    modal_token_id: str = ""
    modal_token_secret: str = ""

    # Platform behaviour
    hard_flag_blocks_pipeline: bool = True
    rate_limit_requests_per_minute: int = 50
    skip_embeddings: bool = False  # set True in dev/test to skip OpenAI embedding calls
    ssl_verify: bool = True  # set False on corporate/VPN networks with proxy certs

    model_config = {"env_file": ".env", "case_sensitive": False}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
