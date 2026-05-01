from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── LLM Provider ─────────────────────────────────────
    # Change llm_provider to swap the model — no engine code changes required.
    # Supported: openai | anthropic | openrouter | ollama
    llm_provider: str = "openai"

    # OpenAI (also used for embeddings regardless of llm_provider)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-large"
    openai_temperature: float = 0.1

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o"

    # Ollama (local — Qwen, Llama, Mistral etc.)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:72b"

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "agentic-platform-dev"

    # LangFuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Cohere
    cohere_api_key: str = ""
    cohere_rerank_model: str = "rerank-english-v3.0"

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
    confidence_threshold: float = 0.75
    max_retry_limit: int = 5
    hard_flag_blocks_pipeline: bool = True
    rate_limit_requests_per_minute: int = 50

    model_config = {"env_file": ".env", "case_sensitive": False}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
