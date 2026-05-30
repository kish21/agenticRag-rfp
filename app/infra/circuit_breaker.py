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
        self._half_open_in_flight = False  # only one trial call probes recovery
        self._lock = Lock()

    def call(self, func, *args, **kwargs):
        with self._lock:
            if self.state == State.OPEN:
                # Guard last_failure_time being None: if the breaker is OPEN
                # without a recorded failure time (e.g. forced/reset), treat the
                # window as not yet elapsed rather than crashing on None math.
                elapsed_ok = (
                    self.last_failure_time is not None
                    and time.time() - self.last_failure_time > self.recovery_timeout
                )
                if elapsed_ok:
                    self.state = State.HALF_OPEN
                    self._half_open_in_flight = True  # this caller is the probe
                else:
                    raise RuntimeError("Circuit breaker is OPEN — service unavailable")
            elif self.state == State.HALF_OPEN:
                # Recovery is being probed by another caller; don't pile on.
                if self._half_open_in_flight:
                    raise RuntimeError("Circuit breaker is HALF_OPEN — probing recovery")
                self._half_open_in_flight = True
        try:
            result = func(*args, **kwargs)
            with self._lock:
                self.failure_count = 0
                self.state = State.CLOSED
                self._half_open_in_flight = False
            return result
        except Exception:
            with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()
                self._half_open_in_flight = False
                if self.failure_count >= self.failure_threshold:
                    self.state = State.OPEN
            raise
