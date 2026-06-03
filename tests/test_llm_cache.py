"""
tests/test_llm_cache.py
========================
Phase 3 PR-A exit criteria for the LLM response cache.

Covers:
  3.4  test_hit_returns_cached
  3.5  test_miss_dispatches_and_stores
  3.6  test_whitespace_sensitivity
  3.7  test_seed_in_key
  3.8  test_cache_bust_forces_miss
  3.9  test_retry_path_misses_cache_via_feedback
  3.10 test_env_disable
  3.11 test_parallel_write_no_error (ON CONFLICT DO NOTHING)
  3.12 test_cost_tracker_cache_fields

Run:
    python -m pytest tests/test_llm_cache.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.fact_store import get_engine  # noqa: E402
from app.infra.cost_tracker import (  # noqa: E402
    RunCostAccumulator,
    record_cache_event,
    set_run_context,
)
from app.providers import llm_cache  # noqa: E402


# ── Fixture: clean cache table around each test ──────────────────────


@pytest.fixture
def cleanup_cache():
    """Yields a tracker callback; deletes recorded cache_keys on teardown."""
    seen: list[str] = []

    def track(k: str) -> None:
        seen.append(k)

    yield track

    engine = get_engine()
    if seen:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "DELETE FROM llm_response_cache WHERE cache_key = ANY(:keys)"
                ),
                {"keys": seen},
            )


@pytest.fixture(autouse=True)
def _ensure_cache_on():
    """Restore LLM_CACHE_ENABLED after a test mutates it."""
    prev = os.environ.get("LLM_CACHE_ENABLED")
    yield
    if prev is None:
        os.environ.pop("LLM_CACHE_ENABLED", None)
    else:
        os.environ["LLM_CACHE_ENABLED"] = prev


def _msgs(text: str = "hello") -> list[dict]:
    return [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": text},
    ]


def _key(messages: list[dict], **kw) -> str:
    return llm_cache.build_cache_key(
        provider=kw.pop("provider", "openai"),
        model=kw.pop("model", "gpt-4o"),
        temperature=kw.pop("temperature", 0.0),
        seed=kw.pop("seed", 1),
        response_format=kw.pop("response_format", None),
        messages=messages,
        cache_bust=kw.pop("cache_bust", None),
    )


# ── 3.4 ──────────────────────────────────────────────────────────────


def test_hit_returns_cached(cleanup_cache):
    """3.4 — store then lookup returns the cached response unchanged."""
    k = _key(_msgs("first"))
    cleanup_cache(k)
    assert llm_cache.store(
        cache_key=k, provider="openai", model="gpt-4o",
        response="cached-response-text", prompt_tokens=100, completion_tokens=50,
    ) is True
    hit = llm_cache.lookup(k)
    assert hit is not None
    assert hit.response == "cached-response-text"
    assert hit.model == "gpt-4o"
    assert hit.prompt_tokens == 100


# ── 3.5 ──────────────────────────────────────────────────────────────


def test_miss_dispatches_and_stores(cleanup_cache):
    """3.5 — lookup on an unknown key returns None; store writes the row."""
    k = _key(_msgs(f"unique-{uuid.uuid4().hex}"))
    cleanup_cache(k)
    assert llm_cache.lookup(k) is None
    assert llm_cache.store(
        cache_key=k, provider="openai", model="gpt-4o",
        response="fresh", prompt_tokens=10, completion_tokens=5,
    ) is True
    assert llm_cache.lookup(k) is not None


# ── 3.6 ──────────────────────────────────────────────────────────────


def test_whitespace_sensitivity(cleanup_cache):
    """3.6 — even a single space-change in the user message produces a new key."""
    a = _key(_msgs("hello world"))
    b = _key(_msgs("hello  world"))   # two spaces
    assert a != b


# ── 3.7 ──────────────────────────────────────────────────────────────


def test_seed_in_key(cleanup_cache):
    """3.7 — same messages, different seed -> different keys."""
    msgs = _msgs("seed-test")
    assert _key(msgs, seed=1) != _key(msgs, seed=2)


# ── 3.8 ──────────────────────────────────────────────────────────────


def test_cache_bust_forces_miss(cleanup_cache):
    """3.8 — identical messages with cache_bust set produce different keys."""
    msgs = _msgs("bust-test")
    no_bust = _key(msgs)
    with_bust = _key(msgs, cache_bust="attempt-2")
    assert no_bust != with_bust


# ── 3.9 ──────────────────────────────────────────────────────────────


def test_retry_path_misses_cache_via_feedback(cleanup_cache):
    """3.9 — Phase 2 retry path appends critic_feedback to messages, which
    naturally produces a different cache key. No use_cache=False needed."""
    base = _msgs("evaluate vendor X")
    feedback = (
        "Previous attempt had grounding_completeness=0.40. "
        "Three claims were ungrounded: ..."
    )
    retry_msgs = base + [{"role": "user", "content": feedback}]
    assert _key(base) != _key(retry_msgs)


# ── 3.10 ─────────────────────────────────────────────────────────────


def test_env_disable():
    """3.10 — LLM_CACHE_ENABLED=false flips llm_cache.enabled() to False."""
    assert llm_cache.enabled() is True  # default
    os.environ["LLM_CACHE_ENABLED"] = "false"
    assert llm_cache.enabled() is False
    os.environ["LLM_CACHE_ENABLED"] = "true"
    assert llm_cache.enabled() is True


# ── 3.11 ─────────────────────────────────────────────────────────────


def test_parallel_write_no_error(cleanup_cache):
    """3.11 — concurrent INSERTs of the same key succeed silently
    (ON CONFLICT DO NOTHING). Exactly one row in the end; the first
    inserter sees True, the rest see False."""
    k = _key(_msgs(f"parallel-{uuid.uuid4().hex}"))
    cleanup_cache(k)

    async def _try():
        return llm_cache.store(
            cache_key=k, provider="openai", model="gpt-4o",
            response="same", prompt_tokens=1, completion_tokens=1,
        )

    async def _gather():
        return await asyncio.gather(*[_try() for _ in range(5)])

    results = asyncio.run(_gather())
    assert sum(1 for r in results if r is True) == 1
    assert sum(1 for r in results if r is False) == 4

    engine = get_engine()
    with engine.connect() as conn:
        n = conn.execute(
            sa.text("SELECT COUNT(*) FROM llm_response_cache WHERE cache_key = :k"),
            {"k": k},
        ).scalar()
    assert n == 1


# ── 3.12 ─────────────────────────────────────────────────────────────


def test_cost_tracker_cache_fields():
    """3.12 — RunCostAccumulator exposes cache_hits / cache_misses /
    cache_savings_usd. record_cache_event populates them."""
    run_id = f"cost-test-{uuid.uuid4().hex[:8]}"
    with set_run_context(run_id, "test") as acc:
        assert acc.cache_hits == 0
        assert acc.cache_misses == 0
        assert acc.cache_savings_usd == 0.0

        record_cache_event(hit=False, model="gpt-4o",
                           prompt_tokens=None, completion_tokens=None)
        record_cache_event(hit=True, model="gpt-4o",
                           prompt_tokens=100, completion_tokens=50)
        record_cache_event(hit=True, model="gpt-4o",
                           prompt_tokens=200, completion_tokens=80)

        assert acc.cache_hits == 2
        assert acc.cache_misses == 1
        assert acc.cache_savings_usd > 0
        s = acc.summary()
        assert s["cache_hits"] == 2
        assert s["cache_misses"] == 1
        assert s["cache_hit_rate"] == pytest.approx(2 / 3, abs=1e-4)
        assert s["cache_savings_usd"] > 0


# ── End-to-end: call_llm() hits cache without provider call ──────────


def test_call_llm_hits_cache_without_provider_call(cleanup_cache):
    """Integration — when a key exists, call_llm() returns the cached
    response and never invokes the provider client (Phase 3 win)."""
    from app.providers.llm import call_llm

    msgs = _msgs(f"e2e-{uuid.uuid4().hex}")
    k = llm_cache.build_cache_key(
        provider="openai", model="gpt-4o", temperature=0.0,
        seed=None, response_format=None, messages=msgs, cache_bust=None,
    )
    # Seed is None at call time but auto-derived inside call_llm() from
    # sha256(messages). We need to reproduce that derivation for the key
    # we pre-store.
    from app.providers.llm import stable_seed
    import json as _json
    derived_seed = stable_seed(_json.dumps(msgs, sort_keys=True, default=str))
    k = llm_cache.build_cache_key(
        provider="openai", model="gpt-4o", temperature=0.0,
        seed=derived_seed, response_format=None, messages=msgs, cache_bust=None,
    )
    cleanup_cache(k)
    llm_cache.store(
        cache_key=k, provider="openai", model="gpt-4o",
        response="PRECACHED", prompt_tokens=1, completion_tokens=1,
    )

    # Any provider-client call would raise — proves we never reached it.
    with patch("app.providers.llm.get_llm_client",
               side_effect=AssertionError("must not be called on cache hit")):
        with set_run_context(f"e2e-{uuid.uuid4().hex[:8]}", "test"):
            result = asyncio.run(call_llm(messages=msgs))

    assert result == "PRECACHED"


# ── Audit finding #2 — read path must NOT write (no write-on-read) ────────


def test_lookup_hit_does_not_write(cleanup_cache):
    """A cache HIT is read-only: lookup() returns the response but must not
    bump hit_count / last_hit_at (the old UPDATE-on-read antipattern). Cache-hit
    metrics live in RunCostAccumulator, not these columns."""
    k = _key(_msgs(f"readonly-{uuid.uuid4().hex}"))
    cleanup_cache(k)
    assert llm_cache.store(
        cache_key=k, provider="openai", model="gpt-4o",
        response="ro-response", prompt_tokens=7, completion_tokens=3,
    ) is True

    # Three hits — would have incremented hit_count to 3 under the old code.
    for _ in range(3):
        hit = llm_cache.lookup(k)
        assert hit is not None and hit.response == "ro-response"

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT hit_count, last_hit_at FROM llm_response_cache "
                "WHERE cache_key = :k"
            ),
            {"k": k},
        ).fetchone()
    assert row.hit_count == 0, "lookup() must not write hit_count on a read"
    assert row.last_hit_at is None, "lookup() must not write last_hit_at on a read"
