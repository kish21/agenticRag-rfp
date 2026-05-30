import asyncio
import time
from collections import deque
from functools import wraps
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
import logging
import openai
from app.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for LLM API calls.
    Enforces max requests per minute with automatic backoff.
    """

    def __init__(self, requests_per_minute: int = None):
        self.rpm = requests_per_minute or settings.rate_limit_requests_per_minute
        self.window = 60.0
        self.timestamps: deque = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a request slot is available."""
        async with self._lock:
            now = time.time()
            while self.timestamps and now - self.timestamps[0] >= self.window:
                self.timestamps.popleft()

            if len(self.timestamps) >= self.rpm:
                wait_time = self.window - (now - self.timestamps[0]) + 0.1
                logger.debug(f"Rate limit: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                now = time.time()
                while self.timestamps and now - self.timestamps[0] >= self.window:
                    self.timestamps.popleft()

            self.timestamps.append(time.time())


# Global rate limiter instance
_rate_limiter = RateLimiter()


# ── Cross-process rate metrics (read by app/jobs/rate_monitor.py) ─────────────
# The monitor runs as a separate Modal cron and cannot see this process's
# in-memory counters, so we persist per-minute counts to Postgres. Best-effort
# and gated by RATE_METRICS_ENABLED — when off (default), the hot path is
# untouched. Never raises into the caller.

def _record_rate_metric(*, calls: int = 0, errors: int = 0) -> None:
    if not getattr(settings, "rate_metrics_enabled", False):
        return
    try:
        import sqlalchemy as sa
        from app.db.fact_store import get_engine
        with get_engine().begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO rate_limit_stats (minute_bucket, total_calls, rate_limit_errors)
                    VALUES (date_trunc('minute', now()), :c, :e)
                    ON CONFLICT (minute_bucket) DO UPDATE SET
                        total_calls = rate_limit_stats.total_calls + EXCLUDED.total_calls,
                        rate_limit_errors = rate_limit_stats.rate_limit_errors + EXCLUDED.rate_limit_errors
                    """
                ),
                {"c": calls, "e": errors},
            )
    except Exception:
        pass  # metrics must never break an LLM call


async def _arecord_rate_metric(*, calls: int = 0, errors: int = 0) -> None:
    """Async wrapper — offloads the sync DB write off the event loop."""
    if not getattr(settings, "rate_metrics_enabled", False):
        return
    await asyncio.to_thread(_record_rate_metric, calls=calls, errors=errors)


def with_retry(max_attempts: int = 5):
    """
    Decorator for LLM API calls with exponential backoff.
    Handles rate limits (429), server errors (500/503), and timeouts.
    """
    def decorator(func):
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=2, max=60),
            retry=retry_if_exception_type((
                openai.RateLimitError,
                openai.APITimeoutError,
                openai.InternalServerError,
                openai.APIConnectionError,
            )),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )
        @wraps(func)
        async def wrapper(*args, **kwargs):
            await _rate_limiter.acquire()
            await _arecord_rate_metric(calls=1)
            try:
                return await func(*args, **kwargs)
            except openai.RateLimitError:
                await _arecord_rate_metric(errors=1)
                raise
        return wrapper
    return decorator


async def call_with_backoff(fn, max_attempts: int = 5):
    """
    Calls an async callable with rate limiting and exponential backoff.
    Used by llm_provider.call_llm() — works across all providers.
    """
    await _rate_limiter.acquire()

    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.InternalServerError,
            openai.APIConnectionError,
        )),
        reraise=True
    )
    async def _call():
        await _arecord_rate_metric(calls=1)
        try:
            return await fn()
        except openai.RateLimitError:
            await _arecord_rate_metric(errors=1)
            raise

    return await _call()


async def call_openai_with_backoff(client, **kwargs):
    """
    Legacy name — wraps client.chat.completions.create() with rate limiting.
    New code should call call_llm() from app.providers.llm instead.
    """
    await _rate_limiter.acquire()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.InternalServerError,
        )),
        reraise=True
    )
    async def _call():
        await _arecord_rate_metric(calls=1)
        try:
            return await client.chat.completions.create(**kwargs)
        except openai.RateLimitError:
            await _arecord_rate_metric(errors=1)
            raise

    return await _call()
