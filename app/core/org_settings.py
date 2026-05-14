"""
Per-org settings. Resolves at request time from:
  1. The org's row in org_settings (if any), else
  2. product.yaml new_org_defaults overlaid with the configured tier preset.

Presets are loaded from app.config.settings.product.presets — product
can rebalance them without code changes.
"""
import time
import threading
import sqlalchemy as sa
from pydantic import BaseModel, Field
from app.db.fact_store import get_engine
from app.config import settings as cfg


CACHE_TTL_SECONDS = cfg.platform.infrastructure.org_settings_cache_ttl_seconds
_cache: dict[str, tuple[float, "OrgSettings"]] = {}
_cache_lock = threading.Lock()


class OrgSettings(BaseModel):
    org_id: str
    quality_tier: str = "balanced"

    use_hyde: bool
    use_reranking: bool
    use_query_rewriting: bool
    use_hybrid_search: bool
    reranker_provider: str
    retrieval_top_k: int
    rerank_top_n: int
    mandatory_check_use_llm_verify: bool

    confidence_retry_threshold: float = Field(ge=0, le=1)
    score_variance_threshold:   float = Field(ge=0, le=1)
    rank_margin_threshold:      int   = Field(ge=0, le=100)
    llm_temperature:            float = Field(ge=0, le=2)

    output_tone: str
    output_language: str
    citation_style: str
    include_confidence_score: bool
    include_evidence_quotes:  bool
    max_evidence_quote_chars: int = Field(ge=50, le=2000)

    parallel_vendors: bool


_ALL_FIELDS = [f for f in OrgSettings.model_fields if f != "org_id"]


def _defaults_for(org_id: str) -> OrgSettings:
    """
    Build defaults by overlaying new_org_defaults + chosen preset.
    All values come from product.yaml — none hardcoded here.
    """
    d = dict(cfg.product.new_org_defaults)
    tier = d.get("quality_tier", "balanced")
    preset = cfg.product.presets.get(tier) or cfg.product.presets["balanced"]
    d.update(preset.config)
    d["quality_tier"] = tier
    return OrgSettings(org_id=org_id, **d)


def get_org_settings(org_id: str) -> OrgSettings:
    now = time.time()
    with _cache_lock:
        if org_id in _cache:
            ts, val = _cache[org_id]
            if now - ts < CACHE_TTL_SECONDS:
                return val

    cols = ", ".join(_ALL_FIELDS)
    eng = get_engine()
    with eng.connect() as conn:
        conn.execute(sa.text("SET LOCAL app.org_id = :o"), {"o": org_id})
        row = conn.execute(sa.text(
            f"SELECT {cols} FROM org_settings WHERE org_id = :o"
        ), {"o": org_id}).fetchone()

    val = (
        OrgSettings(org_id=org_id, **dict(row._mapping))
        if row else _defaults_for(org_id)
    )
    with _cache_lock:
        _cache[org_id] = (now, val)
    return val


def invalidate_org_settings(org_id: str) -> None:
    with _cache_lock:
        _cache.pop(org_id, None)


def upsert_org_settings(org_id: str, updated_by: str, **fields) -> OrgSettings:
    current = get_org_settings(org_id)
    tier = fields.get("quality_tier", current.quality_tier)
    if tier in cfg.product.presets:
        preset = cfg.product.presets[tier].config
        fields = {**preset, **{k: v for k, v in fields.items() if k not in preset},
                  "quality_tier": tier}

    new_state = current.model_copy(update={
        k: v for k, v in fields.items() if k in _ALL_FIELDS or k == "quality_tier"
    })

    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.org_id = :o"), {"o": org_id})
        payload = new_state.model_dump(exclude={"org_id"})
        payload["org_id"] = org_id
        payload["updated_by"] = updated_by
        cols = ", ".join(payload.keys())
        vals = ", ".join(f":{k}" for k in payload.keys())
        sets = ", ".join(
            f"{k} = EXCLUDED.{k}" for k in payload.keys() if k != "org_id"
        )
        conn.execute(sa.text(f"""
            INSERT INTO org_settings ({cols}) VALUES ({vals})
            ON CONFLICT (org_id) DO UPDATE SET {sets}, updated_at = NOW()
        """), payload)

        for field in _ALL_FIELDS:
            old_val = getattr(current, field)
            new_val = getattr(new_state, field)
            if str(old_val) != str(new_val):
                conn.execute(sa.text("""
                    INSERT INTO org_settings_audit
                        (org_id, changed_by, field_name, old_value, new_value)
                    VALUES (:org, :by, :field, :old, :new)
                """), {"org": org_id, "by": updated_by, "field": field,
                       "old": str(old_val), "new": str(new_val)})

    invalidate_org_settings(org_id)
    return get_org_settings(org_id)
