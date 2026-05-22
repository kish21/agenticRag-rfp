import time
from enum import Enum
from threading import Lock


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = State.CLOSED
        self._lock = Lock()

    def call(self, func, *args, **kwargs):
        with self._lock:
            if self.state == State.OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = State.HALF_OPEN
                else:
                    raise RuntimeError("Circuit breaker is OPEN — service unavailable")
        try:
            result = func(*args, **kwargs)
            with self._lock:
                self.failure_count = 0
                self.state = State.CLOSED
            return result
        except Exception:
            with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()
                if self.failure_count >= self.failure_threshold:
                    self.state = State.OPEN
            raise
