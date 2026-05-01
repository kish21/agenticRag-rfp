# SKILL 01 — Environment & Project Foundation
**Sequence:** FIRST. Nothing else starts until this is complete.
**Time:** Half a day.
**Output:** Running local stack, all API keys, Qdrant + PostgreSQL verified.

---

## WHAT THIS SKILL BUILDS — READ FIRST

This platform has **nine agents** that run in sequence for every evaluation:

| # | Agent | Single responsibility |
|---|---|---|
| 1 | Planner | Decomposes RFP evaluation into typed task DAG |
| 2 | Ingestion | LlamaIndex → Qdrant + triggers Extraction Agent |
| 3 | Retrieval | Hybrid search + Cohere Rerank + HyDE |
| 4 | Extraction | Structured facts → PostgreSQL at ingestion time |
| 5 | Evaluation | Reads PostgreSQL facts (NOT Qdrant chunks) |
| 6 | Comparator | SQL join cross-vendor structured comparison |
| 7 | Decision | Governance routing + approval tiers from config |
| 8 | Explanation | Grounded report — every claim cited to source |
| 9 | Critic | Runs after EVERY agent. Only agent that can block. |

**Multi-LLM:** Customers choose their LLM via config. The platform supports:
OpenAI GPT-4o · Anthropic Claude · OpenRouter (any model) · Local/Qwen via Ollama
Zero engine code changes — swap by changing one env var.

**Modal deployment:** Heavy PDF extraction and scheduled jobs run on Modal serverless.
FastAPI handles lightweight endpoints locally or on any cloud.

## WHAT CHANGED FROM PREVIOUS VERSION

- ChromaDB replaced by Qdrant (native dense+sparse, production multi-tenancy)
- LLM provider abstraction added — NOT hardcoded to OpenAI
- Modal SDK added for serverless PDF extraction and scheduled jobs
- LangFuse added alongside LangSmith
- Cohere API key required for reranking
- sentence-transformers for ColBERT offline reranking
- LlamaIndex replaces raw chunking code
- ZIP handler for multi-file vendor submissions

---

## RULES FOR CLAUDE CODE

1. Never skip a verification step
2. Never hardcode secrets in any file
3. Never proceed to Skill 02 until all 9 checkpoints pass

---

## STEP 1 — Verify machine prerequisites

```bash
python --version          # Must be 3.11.x or 3.12.x (fastapi 0.136+ dropped Python 3.9)
node --version            # Must be v20.x.x or higher
docker --version          # Must be 24.x.x or higher
docker compose version    # Must be v2.x.x
git --version
```

---

## STEP 2 — Create project structure

```bash
mkdir agentic-platform && cd agentic-platform

# Core application
mkdir -p app/agents
mkdir -p app/api
mkdir -p app/core
mkdir -p app/db
mkdir -p app/jobs
mkdir -p app/output

# Data and tests
mkdir -p data/documents
mkdir -p data/seed
mkdir -p tests/regression

# Frontend (Next.js)
mkdir -p frontend

# Touch all __init__.py files
find app -type d | xargs -I{} touch {}/__init__.py

# Verification
find app -name "__init__.py" | wc -l
# Must be 7 or more
```

---

## STEP 3 — Create virtual environment

```bash
python -m venv venv
source venv/bin/activate    # Mac/Linux
# venv\Scripts\activate     # Windows

which python
# Must point inside venv/
```

---

## STEP 4 — Create requirements.txt

```text
# ═══════════════════════════════════════════════════════
# requirements.txt — verified against PyPI April 2026
# ═══════════════════════════════════════════════════════
# CRITICAL: install in this exact order to avoid conflicts:
#   pip install -r requirements.txt
# Then verify: pip check  (must return no errors)

# ── LLM and agent orchestration ──────────────────────────
openai==2.33.0              # PyPI Apr 28 2026 — used by OpenAI + OpenRouter providers
anthropic==0.49.0           # PyPI Apr 2026 — for Anthropic Claude provider
langchain==1.2.16           # PyPI Apr 2026 — major version from 0.x, new import paths
langchain-openai==0.3.19    # must match langchain 1.x
langchain-anthropic==0.3.10 # Anthropic Claude via LangChain
langchain-community==0.3.21 # must match langchain 1.x
langgraph==0.4.1            # PyPI Apr 2026 — StateGraph API unchanged
langsmith==0.7.37           # PyPI Apr 2026 — tracing API unchanged
langfuse==4.5.1             # PyPI Apr 2026 — SDK REWRITTEN in v4 March 2026
                            # WARNING: v4 is NOT backwards compatible with v2.x
                            # Read: https://langfuse.com/docs/sdk/python/low-level-sdk

# ── LlamaIndex for document processing ───────────────────
llama-index-core==0.12.6            # PyPI Apr 21 2026 — core package (was llama-index)
llama-index-vector-stores-qdrant==0.6.0
llama-index-embeddings-openai==0.3.0
llama-index-retrievers-bm25==0.5.0
# NOTE: in llama-index 0.12.x, install core + integrations separately
# Do NOT install the old 'llama-index==0.10.x' metapackage

# ── Vector database ───────────────────────────────────────
qdrant-client==1.14.2       # PyPI Apr 2026 — query_points() replaces search() in 1.10+

# ── Reranking ─────────────────────────────────────────────
cohere==5.21.1              # PyPI Mar 2026 — use cohere.ClientV2() not cohere.Client()
sentence-transformers==4.1.0  # PyPI Apr 14 2026 — MAJOR version, CrossEncoder API updated
# ragatouille REMOVED — unmaintained as of 2026, replaced by sentence-transformers 4.x
# ColBERT reranking now available via: from sentence_transformers import CrossEncoder

# ── BM25 keyword search ───────────────────────────────────
rank-bm25==0.2.2            # stable, no changes

# ── Web framework ─────────────────────────────────────────
fastapi==0.136.1            # PyPI Apr 2026 — dropped Python 3.9 support in Feb 2026
uvicorn[standard]==0.34.3   # PyPI Apr 2026 — use [standard] for uvloop
python-multipart==0.0.18    # required by fastapi for file uploads

# ── Document parsing ──────────────────────────────────────
pypdf==5.4.0                # PyPI Apr 2026 — API unchanged from 4.x
python-docx==1.1.2          # stable
pandas==2.2.3               # stable 2.x — no 3.x yet
openpyxl==3.1.5             # stable
python-magic==0.4.27        # stable

# ── Database ──────────────────────────────────────────────
psycopg2-binary==2.9.10     # stable
sqlalchemy==2.0.40          # stable 2.0.x patch series
alembic==1.14.1             # stable

# ── HTTP and utilities ────────────────────────────────────
httpx==0.28.1               # PyPI Apr 2026
python-dotenv==1.1.0        # stable
pydantic-settings==2.7.0    # must match pydantic 2.x
pydantic==2.11.3            # PyPI Apr 2026 — @validator still works but shows deprecation warning
                            # Use @field_validator in all new code (see Skill 02 output_models.py)
tenacity==9.0.0             # PyPI Apr 2026 — retry API unchanged

# ── Output generation ─────────────────────────────────────
reportlab==4.2.5            # stable
weasyprint==63.1            # PyPI Apr 2026

# ── Deployment ────────────────────────────────────────────
modal>=0.64.0               # floor constraint — always installs latest stable

# ── Testing and dev ───────────────────────────────────────
pytest==8.3.5               # PyPI Apr 2026
pytest-asyncio==0.25.3      # PyPI Apr 2026
faker==37.0.0               # PyPI Apr 2026
```

```bash
pip install -r requirements.txt
# Takes 5-8 minutes

python -c "
import openai, langchain, langgraph, langsmith, langfuse
import llama_index.core, qdrant_client, cohere, fastapi, pydantic
print('openai:', openai.__version__)       # must be 2.x
print('langchain:', langchain.__version__) # must be 1.x
print('langfuse:', langfuse.__version__)   # must be 4.x
print('fastapi:', fastapi.__version__)     # must be 0.13x
print('All packages OK')
"
```

---

## STEP 5 — Obtain all API keys

### OpenAI
- platform.openai.com → API Keys → Create new key
- Set monthly budget limit £20

### LangSmith (free)
- smith.langchain.com → Settings → API Keys
- Starts with `ls__`

### LangFuse (free)
- cloud.langfuse.com → Settings → API Keys
- Two keys: Public key and Secret key

### Cohere (free tier)
- dashboard.cohere.com → API Keys → Create key
- Free tier: 1000 calls/month — enough for development

### Modal
```bash
modal token new
modal profile current
# Must print your username
```

### Qdrant (local — no key needed for dev)
Docker runs Qdrant locally. No API key for local development.
For cloud: cloud.qdrant.io (free 1GB cluster)

### Slack Bot Token
- api.slack.com/apps → Create App → OAuth & Permissions
- Add scope: chat:write → Install → Copy xoxb- token

---

## STEP 6 — Create .env

```bash
# ── LLM Provider (choose one, or configure per agent) ────
# Options: openai | anthropic | openrouter | ollama
LLM_PROVIDER=openai

# ── OpenAI (used when LLM_PROVIDER=openai or for embeddings) ─
OPENAI_API_KEY=sk-proj-your-key
OPENAI_MODEL=gpt-4o
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_TEMPERATURE=0.1

# ── Anthropic (used when LLM_PROVIDER=anthropic) ─────────
ANTHROPIC_API_KEY=sk-ant-your-key
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# ── OpenRouter (used when LLM_PROVIDER=openrouter) ───────
# Gives access to 200+ models via one API key
OPENROUTER_API_KEY=sk-or-your-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openai/gpt-4o

# ── Ollama local (used when LLM_PROVIDER=ollama) ─────────
# Runs Qwen, Llama, Mistral etc. locally — no API key needed
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:72b

# ── LangSmith ────────────────────────────────────────────
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__your-key
LANGCHAIN_PROJECT=agentic-platform-dev

# ── LangFuse ─────────────────────────────────────────────
LANGFUSE_PUBLIC_KEY=pk-lf-your-key
LANGFUSE_SECRET_KEY=sk-lf-your-key
LANGFUSE_HOST=https://cloud.langfuse.com

# ── Cohere ────────────────────────────────────────────────
COHERE_API_KEY=your-cohere-key
COHERE_RERANK_MODEL=rerank-english-v3.0

# ── App security ─────────────────────────────────────────
APP_API_KEY=your-32-char-random-key
# python -c "import secrets; print(secrets.token_hex(32))"

# ── Qdrant ────────────────────────────────────────────────
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_PREFIX=platform

# ── Database ─────────────────────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=agenticplatform
POSTGRES_USER=platformuser
POSTGRES_PASSWORD=platformpass2026

# ── Slack ────────────────────────────────────────────────
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_CHANNEL_ID=C0XXXXXXXXX

# ── Platform ─────────────────────────────────────────────
CONFIDENCE_THRESHOLD=0.75
MAX_RETRY_LIMIT=5
HARD_FLAG_BLOCKS_PIPELINE=true
RATE_LIMIT_REQUESTS_PER_MINUTE=50
```

---

## STEP 7 — Create .gitignore

```gitignore
.env
*.env.local
venv/
__pycache__/
*.pyc
.pytest_cache/
data/documents/
data/qdrant/
node_modules/
frontend/.next/
frontend/out/
.modal/
*.egg-info/
.idea/
.vscode/
```

---

## STEP 8 — Create docker-compose.yml

```yaml
version: '3.9'

services:
  postgres:
    image: postgres:15
    container_name: platform_postgres
    environment:
      POSTGRES_DB: agenticplatform
      POSTGRES_USER: platformuser
      POSTGRES_PASSWORD: platformpass2026
    ports:
      - '5432:5432'
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U platformuser -d agenticplatform']
      interval: 10s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    container_name: platform_qdrant
    ports:
      - '6333:6333'
      - '6334:6334'
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ['CMD-SHELL', 'curl -f http://localhost:6333/healthz || exit 1']
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  qdrant_data:
```

```bash
docker compose up -d
sleep 20

# Verify Qdrant
curl http://localhost:6333/healthz
# Must return: {"title":"qdrant - vector search engine","version":"..."}

# Verify PostgreSQL
docker compose ps
# Both must show "healthy"
```

---

## STEP 9 — Create app/config.py

```python
# app/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── LLM Provider abstraction ─────────────────────────
    # Change llm_provider to switch the model the platform uses.
    # No engine code changes required. Supported values:
    #   openai      — OpenAI GPT-4o (default)
    #   anthropic   — Anthropic Claude
    #   openrouter  — Any model via OpenRouter API
    #   ollama      — Local models (Qwen, Llama, Mistral via Ollama)
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
    langchain_api_key: str
    langchain_project: str = "agentic-platform-dev"

    # LangFuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Cohere
    cohere_api_key: str = ""
    cohere_rerank_model: str = "rerank-english-v3.0"

    # App
    app_api_key: str

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_prefix: str = "platform"

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "agenticplatform"
    postgres_user: str = "platformuser"
    postgres_password: str

    # Slack
    slack_bot_token: str = ""
    slack_channel_id: str = ""

    # Platform behaviour
    confidence_threshold: float = 0.75
    max_retry_limit: int = 5
    hard_flag_blocks_pipeline: bool = True
    rate_limit_requests_per_minute: int = 50

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK01-CP04
# Must print config loads OK
```

---

## STEP 9b — Create app/core/llm_provider.py

This is the single file that makes the platform model-agnostic.
Every agent calls `get_llm_client()` — never imports openai directly.

```python
# app/core/llm_provider.py
"""
Model-agnostic LLM abstraction.
Swap providers by changing LLM_PROVIDER in .env — zero engine code changes.

Supported providers (April 2026):
  openai      — OpenAI GPT-4o via openai 2.x SDK
  anthropic   — Anthropic Claude via anthropic 0.49 SDK
  openrouter  — Any model via OpenRouter (openai SDK, different base_url)
  ollama      — Local models (Qwen, Llama, Mistral) via Ollama REST API
"""
from typing import Optional
from app.config import settings


def get_llm_client():
    """
    Returns an LLM client configured for the active provider.
    All clients expose the same .chat() interface used by agents.
    """
    provider = settings.llm_provider.lower()

    if provider == "openai":
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=settings.openai_api_key)

    elif provider == "anthropic":
        from anthropic import AsyncAnthropic
        return AsyncAnthropic(api_key=settings.anthropic_api_key)

    elif provider == "openrouter":
        # OpenRouter uses the OpenAI SDK with a different base_url
        # This gives access to Claude, Qwen, Llama, Gemini etc.
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )

    elif provider == "ollama":
        # Ollama runs Qwen 2.5, Llama 3, Mistral etc. locally
        # Uses OpenAI-compatible API — no API key required
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key="ollama",  # placeholder, Ollama ignores auth
            base_url=f"{settings.ollama_base_url}/v1",
        )

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: '{provider}'. "
            f"Valid options: openai, anthropic, openrouter, ollama"
        )


def get_model_name() -> str:
    """Returns the model name string for the active provider."""
    provider = settings.llm_provider.lower()
    mapping = {
        "openai": settings.openai_model,
        "anthropic": settings.anthropic_model,
        "openrouter": settings.openrouter_model,
        "ollama": settings.ollama_model,
    }
    return mapping.get(provider, settings.openai_model)


async def call_llm(
    messages: list[dict],
    temperature: float = 0.1,
    max_tokens: int = 4096,
    response_format: Optional[dict] = None,
) -> str:
    """
    Unified LLM call across all providers.
    Agents call this — never the provider SDK directly.
    Returns: the text content of the response.
    """
    from app.core.rate_limiter import call_with_backoff

    provider = settings.llm_provider.lower()
    client = get_llm_client()

    if provider == "anthropic":
        # Anthropic SDK has different message format — system goes separately
        system_msg = next(
            (m["content"] for m in messages if m["role"] == "system"), None
        )
        user_msgs = [m for m in messages if m["role"] != "system"]

        async def _call():
            resp = await client.messages.create(
                model=get_model_name(),
                max_tokens=max_tokens,
                system=system_msg or "You are a helpful assistant.",
                messages=user_msgs,
            )
            return resp.content[0].text

        return await call_with_backoff(_call)

    else:
        # OpenAI, OpenRouter, Ollama — all use chat.completions.create
        kwargs = dict(
            model=get_model_name(),
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_format:
            kwargs["response_format"] = response_format

        async def _call():
            resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content

        return await call_with_backoff(_call)
```

**Checkpoint SK01-CP09b** — run after creating this file:
```bash
python -c "
from app.core.llm_provider import get_llm_client, get_model_name
client = get_llm_client()
print('LLM provider:', type(client).__name__)
print('Model:', get_model_name())
print('llm_provider.py OK')
"
```

---

## STEP 10 — Create app/main.py skeleton

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Enterprise Agentic AI Platform",
        version="1.0.0"
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app_api_key and ["*"] or ["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "version": "1.0.0",
            "skill": "01-foundation"
        }

    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=8000, reload=True)
```

---

## STEP 11 — Create app_modal.py (Modal deployment)

Modal handles two things: heavy PDF extraction (CPU/GPU burst) and scheduled jobs.
FastAPI handles all real-time API requests. They share the same database.

```python
# app_modal.py
"""
Modal serverless deployment.

What runs on Modal:
  - Heavy PDF extraction (large files, scanned PDFs, OCR)
  - Daily cleanup jobs (orphaned runs, old chunks)
  - Rate monitoring (every 30 minutes)

What runs on FastAPI (local or any cloud):
  - All real-time API endpoints
  - Agent orchestration (LangGraph)
  - Retrieval and evaluation

Why Modal for PDF extraction:
  - Burst CPU/GPU for large documents (200+ pages)
  - No timeout limits (local FastAPI times out at 30s)
  - Scales to 20 concurrent vendor document ingestions
"""
import modal
from modal import App, Image, Secret, Volume

# ── Modal app definition ──────────────────────────────────
app = App("agentic-platform")

# Docker image with all PDF processing dependencies
pdf_image = (
    Image.debian_slim(python_version="3.11")
    .pip_install(
        "pypdf==5.4.0",
        "python-docx==1.1.2",
        "python-magic==0.4.27",
        "llama-index-core==0.12.6",
        "llama-index-vector-stores-qdrant==0.6.0",
        "qdrant-client==1.14.2",
        "openai==2.33.0",
        "anthropic==0.49.0",   # for Anthropic provider
        "sqlalchemy==2.0.40",
        "psycopg2-binary==2.9.10",
        "pydantic==2.11.3",
        "pydantic-settings==2.7.0",
        "python-dotenv==1.1.0",
    )
    .apt_install("libmagic1")   # required by python-magic
)

# Shared secrets — reads from Modal secret store, same values as .env
platform_secrets = Secret.from_name("agentic-platform-secrets")


# ── PDF Extraction function ───────────────────────────────
@app.function(
    image=pdf_image,
    secrets=[platform_secrets],
    timeout=600,           # 10 minutes for large documents
    memory=2048,           # 2GB RAM for large PDFs
    cpu=2,
)
async def extract_pdf_on_modal(
    file_bytes: bytes,
    filename: str,
    org_id: str,
    vendor_id: str,
    run_id: str,
) -> dict:
    """
    Runs PDF extraction on Modal serverless infrastructure.
    Called by the Ingestion Agent for large or complex documents.
    Returns extraction result dict matching IngestionOutput schema.
    """
    import io
    from app.agents.ingestion import run_ingestion_for_file

    # Run the same ingestion logic — Modal just provides more resources
    result = await run_ingestion_for_file(
        file_bytes=file_bytes,
        filename=filename,
        org_id=org_id,
        vendor_id=vendor_id,
        run_id=run_id,
    )
    return result.model_dump()


# ── Scheduled cleanup job ─────────────────────────────────
@app.function(
    image=pdf_image,
    secrets=[platform_secrets],
    schedule=modal.Period(hours=24),  # runs daily
)
async def daily_cleanup():
    """
    Daily cleanup: removes orphaned evaluation runs,
    chunks from failed ingestions, expired sessions.
    """
    from app.jobs.cleanup import run_cleanup
    result = await run_cleanup()
    print(f"Cleanup complete: {result}")


# ── Rate monitor ──────────────────────────────────────────
@app.function(
    image=pdf_image,
    secrets=[platform_secrets],
    schedule=modal.Period(minutes=30),
)
async def rate_monitor():
    """
    Every 30 minutes: check LangFuse for hard flag rate spikes.
    Alerts via Slack if hard_flag_rate > 5%.
    """
    from app.jobs.rate_monitor import check_flag_rates
    await check_flag_rates()


# ── Local entry point for testing ────────────────────────
if __name__ == "__main__":
    # Test Modal connection without deploying
    print("Modal app defined. Deploy with: modal deploy app_modal.py")
    print("Test locally with: modal run app_modal.py::extract_pdf_on_modal")
```

**Deploy to Modal:**
```bash
# First time: create secrets in Modal dashboard
modal secret create agentic-platform-secrets \
    OPENAI_API_KEY=your-key \
    ANTHROPIC_API_KEY=your-key \
    QDRANT_HOST=your-qdrant-host \
    POSTGRES_PASSWORD=your-password

# Deploy
modal deploy app_modal.py
# Output: Created function extract_pdf_on_modal
#         Created schedule daily_cleanup
#         Created schedule rate_monitor
```

---

## FINAL VERIFICATION — All 9 must pass

```bash
python checkpoint_runner.py SK01-CP01   # Python 3.11
python checkpoint_runner.py SK01-CP02   # Venv active
python checkpoint_runner.py SK01-CP03   # All packages
python checkpoint_runner.py SK01-CP04   # Config loads
python checkpoint_runner.py SK01-CP05   # Docker + PostgreSQL healthy
python checkpoint_runner.py SK01-CP06   # Qdrant healthy
python checkpoint_runner.py SK01-CP07   # FastAPI /health 200
python checkpoint_runner.py SK01-CP08   # .env not in git
python checkpoint_runner.py SK01-CP09   # Modal authenticated

# All 9 must show PASS before opening SKILL_02
```

---

## HAND-OFF TO SKILL 02

State in CLAUDE.md: current_skill = SKILL_02, last_checkpoint = SK01-CP09
Open skills/SKILL_02_PLANNER_AND_CRITIC.md
