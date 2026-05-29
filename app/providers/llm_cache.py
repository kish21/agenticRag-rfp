"""
Phase 3 — LLM response cache wrapper.

Content-addressed cache keyed on
    sha256(provider | model | temperature | seed | response_format |
           system_messages | user_messages | cache_bust)

Tenant-blind by design — see docs/dev/PRODUCTION_READINESS_PLAN.md
Phase 3 "Tenant blindness" subsection. Do not key by org_id.

Public surface:
    enabled() -> bool
    build_cache_key(...)
    lookup(cache_key) -> Optional[CachedResponse]
    store(cache_key, ...)

Wired into `call_llm()` in app/providers/llm.py.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import sqlalchemy as sa

logger = logging.getLogger("phase3.llm_cache")


_TRUE = ("1", "true", "yes", "on")


def enabled() -> bool:
    """Process-wide cache toggle. Default ON; set LLM_CACHE_ENABLED=false to disable."""
    return os.getenv("LLM_CACHE_ENABLED", "true").lower() in _TRUE


@dataclass(frozen=True)
class CachedResponse:
    response: str
    provider: str
    model: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]


def build_cache_key(
    *,
    provider: str,
    model: str,
    temperature: float,
    seed: Optional[int],
    response_format: Optional[dict],
    messages: list[dict],
    cache_bust: Optional[str],
) -> str:
    """SHA256 over the canonicalised inputs. Whitespace-sensitive."""
    payload = {
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "seed": seed,
        "response_format": response_format,
        "messages": messages,
        "cache_bust": cache_bust,
    }
    canonical = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def lookup(cache_key: str) -> Optional[CachedResponse]:
    """Returns the cached response if present + increments hit_count + last_hit_at."""
    from app.db.fact_store import get_engine  # local import to keep startup light

    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            sa.text(
                """
                UPDATE llm_response_cache
                SET hit_count = hit_count + 1,
                    last_hit_at = now()
                WHERE cache_key = :k
                RETURNING response, provider, model, prompt_tokens, completion_tokens
                """
            ),
            {"k": cache_key},
        ).fetchone()
    if row is None:
        return None
    return CachedResponse(
        response=row.response,
        provider=row.provider,
        model=row.model,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
    )


def store(
    *,
    cache_key: str,
    provider: str,
    model: str,
    response: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
) -> bool:
    """
    Stores a fresh response. Returns True if inserted, False on UNIQUE
    conflict (another concurrent caller stored the same key first — that
    is fine, both calls produced identical content).
    """
    from app.db.fact_store import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            sa.text(
                """
                INSERT INTO llm_response_cache
                    (cache_key, provider, model, response,
                     prompt_tokens, completion_tokens)
                VALUES
                    (:k, :p, :m, :r, :pt, :ct)
                ON CONFLICT (cache_key) DO NOTHING
                RETURNING cache_key
                """
            ),
            {
                "k": cache_key,
                "p": provider,
                "m": model,
                "r": response,
                "pt": prompt_tokens,
                "ct": completion_tokens,
            },
        ).fetchone()
    return row is not None
