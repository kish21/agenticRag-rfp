"""
Phase 4 — bounded concurrency for per-vendor parallel execution.

LangGraph's Send API fans out N parallel branches with no built-in throttle.
For a 15-vendor RFP, naively firing 15 concurrent LLM + Qdrant requests would:
  • Hit OpenAI's tokens-per-minute (TPM) rate limit and trigger backoff cascades
  • Exhaust the Qdrant client connection pool
  • Saturate the LangSmith tracer's batched HTTP queue

This module exposes a single asyncio.Semaphore that every per-vendor node
acquires before doing real work. LangGraph still spawns all N branches
immediately, but only MAX_VENDOR_CONCURRENCY of them run their LLM / Qdrant
calls at any moment; the rest wait at the semaphore.

Tuning:
  • Default 5 — chosen to fit OpenAI tier-1 TPM budgets comfortably.
  • Override with environment variable: MAX_VENDOR_CONCURRENCY=8.
  • For a single-vendor smoke test it doesn't matter.

The semaphore is module-level singleton so all per-vendor nodes in the same
process share one budget. Use `async with vendor_slot():` inside each
per-vendor node body to claim a slot.
"""
import asyncio
import os
from contextlib import asynccontextmanager


def _read_concurrency_limit() -> int:
    raw = os.getenv("MAX_VENDOR_CONCURRENCY", "5")
    try:
        n = int(raw)
    except ValueError:
        n = 5
    return max(1, n)   # Never allow 0 — would deadlock the pipeline.


MAX_VENDOR_CONCURRENCY = _read_concurrency_limit()
_vendor_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """Lazy initialisation — Semaphore must be created in the running event loop
    if we want it tied to that loop. Lazy-init via first access means the
    semaphore lives in whatever loop the first per-vendor node runs in."""
    global _vendor_semaphore
    if _vendor_semaphore is None:
        _vendor_semaphore = asyncio.Semaphore(MAX_VENDOR_CONCURRENCY)
    return _vendor_semaphore


@asynccontextmanager
async def vendor_slot():
    """Acquire one concurrency slot for a per-vendor node body.

    Usage:
        async def retrieval_per_vendor(state):
            async with vendor_slot():
                # ... LLM + Qdrant work ...
    """
    sem = _get_semaphore()
    async with sem:
        yield


def reset_for_tests(new_limit: int | None = None) -> None:
    """Test-only helper: drop the singleton so a new limit can take effect.
    Production code must NEVER call this."""
    global _vendor_semaphore, MAX_VENDOR_CONCURRENCY
    if new_limit is not None:
        MAX_VENDOR_CONCURRENCY = max(1, int(new_limit))
    _vendor_semaphore = None
