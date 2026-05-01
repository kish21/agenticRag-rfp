"""
Compute provider abstraction for burst jobs and scheduled tasks.
Mirrors the pattern of llm_provider.py — swap provider via COMPUTE_PROVIDER in .env.

Supported providers:
  modal           — Modal serverless (default, zero infra setup)
  aws_lambda      — AWS Lambda + EventBridge scheduled triggers   [Skill 09]
  azure_functions — Azure Functions with Timer trigger            [Skill 09]
  gcp_cloudrun    — GCP Cloud Run Jobs + Cloud Scheduler          [Skill 09]
  local_worker    — On-premise Celery worker (air-gapped/no cloud) [Skill 09]

Usage in agents:
    from app.core.compute_provider import get_compute_backend
    extract_fn = get_compute_backend()
    result = await extract_fn(file_bytes=..., filename=..., org_id=..., vendor_id=..., run_id=...)
"""
from app.config import settings


def get_compute_backend():
    """
    Returns the extraction function for the active compute provider.
    All backends accept the same signature: (file_bytes, filename, org_id, vendor_id, run_id).
    """
    provider = settings.compute_provider.lower()

    if provider == "modal":
        from app_modal import extract_pdf_on_modal
        return extract_pdf_on_modal

    elif provider == "local_worker":
        raise NotImplementedError(
            "COMPUTE_PROVIDER='local_worker' (on-premise Celery) is implemented in Skill 09. "
            "Use COMPUTE_PROVIDER='modal' for now."
        )

    elif provider == "aws_lambda":
        raise NotImplementedError(
            "COMPUTE_PROVIDER='aws_lambda' is implemented in Skill 09. "
            "Use COMPUTE_PROVIDER='modal' for now."
        )

    elif provider == "azure_functions":
        raise NotImplementedError(
            "COMPUTE_PROVIDER='azure_functions' is implemented in Skill 09. "
            "Use COMPUTE_PROVIDER='modal' for now."
        )

    elif provider == "gcp_cloudrun":
        raise NotImplementedError(
            "COMPUTE_PROVIDER='gcp_cloudrun' is implemented in Skill 09. "
            "Use COMPUTE_PROVIDER='modal' for now."
        )

    else:
        raise ValueError(
            f"Unknown COMPUTE_PROVIDER: '{provider}'. "
            f"Valid options: modal, aws_lambda, azure_functions, gcp_cloudrun, local_worker"
        )
