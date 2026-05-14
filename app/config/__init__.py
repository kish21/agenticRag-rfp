"""
Four-layer configuration loader.

Layer 1 — .env (secrets)
Layer 2 — platform.yaml (engineering)
Layer 3 — product.yaml (product/business)
Layer 4 — org_settings table (per-org, loaded separately)

Usage:
    from app.config import settings
    settings.platform.retrieval.embedding_model
    settings.product.presets['balanced'].config['use_hyde']
    settings.openai_api_key
"""
from app.config.loader import settings

__all__ = ["settings"]
