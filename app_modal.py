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
from modal import App, Image, Secret

app = App("agentic-platform")

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

platform_secrets = Secret.from_name("agentic-platform-secrets")


@app.function(
    image=pdf_image,
    secrets=[platform_secrets],
    timeout=600,
    memory=2048,
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
    image=pdf_image,
    secrets=[platform_secrets],
    schedule=modal.Period(hours=24),
)
async def daily_cleanup():
    """Daily cleanup: removes orphaned evaluation runs, failed ingestion chunks, expired sessions."""
    from app.jobs.cleanup import run_cleanup
    result = await run_cleanup()
    print(f"Cleanup complete: {result}")


@app.function(
    image=pdf_image,
    secrets=[platform_secrets],
    schedule=modal.Period(minutes=30),
)
async def rate_monitor():
    """Every 30 minutes: check LangFuse for hard flag rate spikes. Alerts via Slack if >5%."""
    from app.jobs.rate_monitor import check_flag_rates
    await check_flag_rates()


if __name__ == "__main__":
    print("Modal app defined. Deploy with: modal deploy app_modal.py")
    print("Test locally with: modal run app_modal.py::extract_pdf_on_modal")
