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
            return await func(*args, **kwargs)
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
            Exception,
        )),
        reraise=True
    )
    async def _call():
        return await fn()

    return await _call()


async def call_openai_with_backoff(client, **kwargs):
    """
    Legacy name — wraps client.chat.completions.create() with rate limiting.
    New code should call call_llm() from app.core.llm_provider instead.
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
        return await client.chat.completions.create(**kwargs)

    return await _call()
