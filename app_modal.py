"""
Modal serverless deployment.

What runs on Modal:
  - Heavy PDF extraction (large files, scanned PDFs, OCR)       → pdf_image, CPU
  - Open-source batch embeddings (BGE on GPU)                   → embed_image, A10G
  - LLM inference — Qwen 2.5 72B AWQ via vLLM                  → llm_image, A100-80GB
  - LLM fine-tuning — domain-specific (procurement/HR/legal)    → llm_image, H100 (future)
  - Daily cleanup + rate monitoring                             → pdf_image (needs cloud PG)

What runs on FastAPI (local or any cloud):
  - All real-time API endpoints
  - Agent orchestration (LangGraph)
  - Retrieval and evaluation

GPU allocation:
  A10G  (~$1.10/hr) — embeddings (embed_image)
  A100  (~$3.70/hr) — LLM inference (llm_image, Qwen 2.5 72B AWQ fits in 80GB)
  H100  (~$4.20/hr) — fine-tuning jobs (future)
"""
import modal
from modal import App, Image, Secret

app = App("agentic-platform")

platform_secrets = Secret.from_name("agentic-platform-secrets", environment_name="rag")

pdf_image = (
    Image.debian_slim(python_version="3.11")
    .pip_install(
        "pypdf==5.4.0",
        "python-docx==1.1.2",
        "python-magic==0.4.27",
        "llama-index-core==0.14.21",
        "llama-index-vector-stores-qdrant==0.10.0",
        "qdrant-client==1.17.1",
        "openai==2.33.0",
        "anthropic==0.97.0",
        "sqlalchemy==2.0.40",
        "psycopg2-binary==2.9.10",
        "pydantic==2.13.3",
        "pydantic-settings==2.14.0",
        "python-dotenv==1.1.0",
    )
    .apt_install("libmagic1")
)

# ── LLM inference — Qwen 2.5 72B AWQ on A100-80GB ───────────────────────────
# AWQ 4-bit quantisation: ~36-40GB VRAM → fits comfortably in A100-80GB.
# Model weights are stored in a Modal Volume so cold starts don't re-download.
# Exposes OpenAI-compatible /v1/chat/completions — zero agent code changes.
# After deploy, set MODAL_LLM_ENDPOINT in .env to the printed URL.

QWEN_MODEL_ID   = "Qwen/Qwen2.5-72B-Instruct-AWQ"
QWEN_SERVED_NAME = "qwen2.5-72b"
LLM_VOLUME_PATH  = "/llm-weights"
LLM_PORT         = 8000

llm_volume = modal.Volume.from_name("agentic-llm-weights", create_if_missing=True)

llm_image = (
    Image.from_registry("vllm/vllm-openai:v0.6.6.post1")   # pre-built: CUDA + PyTorch + vLLM tested together
    .pip_install(
        "huggingface-hub==0.23.4",
        "hf-transfer==0.1.6",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)


@app.function(
    image=llm_image,
    gpu="a100-80gb",
    secrets=[platform_secrets],
    timeout=7200,                   # 2 hours — long-running server
    volumes={LLM_VOLUME_PATH: llm_volume},
    min_containers=0,               # cold start — no idle billing (A100 costs ~$3.70/hr warm)
)
@modal.concurrent(max_inputs=32)   # vLLM handles concurrency internally
@modal.web_server(LLM_PORT, startup_timeout=600)
def serve_llm_on_modal():
    """
    Serves Qwen 2.5 72B via vLLM on an A100-80GB GPU.
    Exposes OpenAI-compatible API at /v1/chat/completions.

    Usage — set in .env after deploy:
        LLM_PROVIDER=modal
        MODAL_LLM_ENDPOINT=https://<your-workspace>--agentic-platform-serve-llm-on-modal.modal.run
        MODAL_LLM_MODEL=qwen2.5-72b

    Fine-tuning path: train a domain-specific model, save weights to llm_volume,
    then change QWEN_MODEL_ID to point to the fine-tuned checkpoint.
    """
    import subprocess
    subprocess.Popen([
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model",                QWEN_MODEL_ID,
        "--quantization",         "awq",
        "--download-dir",         LLM_VOLUME_PATH,
        "--host",                 "0.0.0.0",
        "--port",                 str(LLM_PORT),
        "--served-model-name",    QWEN_SERVED_NAME,
        "--max-model-len",        "32768",   # 32K context — safe for 80GB with AWQ
        "--tensor-parallel-size", "1",
        "--dtype",                "auto",
        "--trust-remote-code",
    ])


@app.function(
    image=llm_image,
    gpu="a100-80gb",
    secrets=[platform_secrets],
    timeout=3600,
    volumes={LLM_VOLUME_PATH: llm_volume},
)
def download_llm_weights():
    """
    One-time setup: pre-downloads Qwen 2.5 72B AWQ weights into the Modal Volume.
    Run before first deploy so serve_llm_on_modal starts instantly (no download lag).

    Run with:
        modal run app_modal.py::download_llm_weights --env rag
    """
    import os
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
    from huggingface_hub import snapshot_download
    snapshot_download(
        repo_id=QWEN_MODEL_ID,
        local_dir=f"{LLM_VOLUME_PATH}/{QWEN_MODEL_ID}",
        ignore_patterns=["*.pt", "*.gguf"],  # prefer .safetensors
    )
    llm_volume.commit()
    print(f"Weights cached at: {LLM_VOLUME_PATH}/{QWEN_MODEL_ID}")
    print("You can now deploy: modal deploy app_modal.py --env rag")


# ── Separate image for open-source embedding — sentence-transformers + torch only.
# Used when EMBEDDING_PROVIDER=modal. GPU A10G gives ~10x throughput vs CPU
# for batch ingestion (hundreds of chunks per document).
embed_image = (
    Image.debian_slim(python_version="3.11")
    .pip_install(
        "sentence-transformers==4.1.0",
        "torch==2.3.0",
        "numpy==1.26.4",
    )
)

@app.function(
    image=pdf_image,
    secrets=[platform_secrets],
    timeout=600,
    memory=2048,
    cpu=2,
    min_containers=0,  # cold start only — no idle billing
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
    from app.agents.ingestion import run_ingestion_for_file

    result = await run_ingestion_for_file(
        file_bytes=file_bytes,
        filename=filename,
        org_id=org_id,
        vendor_id=vendor_id,
        run_id=run_id,
    )
    return result.model_dump()


@app.function(
    image=embed_image,
    gpu="A10G",
    secrets=[platform_secrets],
    timeout=120,
    min_containers=0,
)
def embed_batch_on_modal(texts: list[str], model_name: str) -> list[list[float]]:
    """
    Batch-embed texts on Modal GPU. Called by embedding_provider.py when
    EMBEDDING_PROVIDER=modal during document ingestion.
    GPU processes hundreds of chunks in parallel — ~10x faster than local CPU.
    Model is cached in the container after first load.
    """
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name, trust_remote_code=True)
    embeddings = model.encode(
        [t[:8000] for t in texts],
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=64,
    )
    return embeddings.tolist()


@app.function(
    image=embed_image,
    gpu="A10G",
    secrets=[platform_secrets],
    timeout=60,
    min_containers=0,
)
def embed_single_on_modal(text: str, model_name: str) -> list[float]:
    """
    Single-text embedding on Modal GPU. Available for scheduled/batch jobs.
    For live retrieval queries, prefer local CPU via EMBEDDING_PROVIDER=local
    to avoid Modal cold-start latency on every search.
    """
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name, trust_remote_code=True)
    return model.encode([text[:8000]], normalize_embeddings=True)[0].tolist()


# ── PRODUCTION TODO ───────────────────────────────────────────────────────────
# daily_cleanup and rate_monitor are disabled until PostgreSQL moves to cloud.
# Both functions connect directly to the database and cannot reach localhost.
# To re-enable for production:
#   1. Provision a cloud PostgreSQL (Neon / Supabase / Railway)
#   2. Update POSTGRES_HOST / POSTGRES_PORT / POSTGRES_USER / POSTGRES_PASSWORD
#      in the Modal secret: modal secret create agentic-platform-secrets ... --env rag
#   3. Uncomment the two functions below and redeploy: modal deploy app_modal.py --env rag
# ─────────────────────────────────────────────────────────────────────────────

# @app.function(
#     image=pdf_image,
#     secrets=[platform_secrets],
#     schedule=modal.Period(hours=24),
#     min_containers=0,
# )
# async def daily_cleanup():
#     """Daily cleanup: removes orphaned runs, expired chunks. Needs cloud PostgreSQL."""
#     from app.jobs.cleanup import run_cleanup
#     result = await run_cleanup()
#     print(f"Cleanup complete: {result}")


# @app.function(
#     image=pdf_image,
#     secrets=[platform_secrets],
#     schedule=modal.Period(minutes=30),
#     min_containers=0,
# )
# async def rate_monitor():
#     """Every 30 minutes: check LangFuse for hard flag rate spikes. Needs cloud PostgreSQL."""
#     from app.jobs.rate_monitor import check_flag_rates
#     await check_flag_rates()


if __name__ == "__main__":
    print("Modal app defined. Deploy with: modal deploy app_modal.py")
    print("Test locally with: modal run app_modal.py::extract_pdf_on_modal")
