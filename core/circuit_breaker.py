from __future__ import annotations

import time
from threading import Lock
from typing import Dict


class CircuitState:
    def __init__(self) -> None:
        self.failures = 0
        self.last_failure_at: float | None = None
        self.open_until: float | None = None


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_seconds: int = 30) -> None:
        self._states: Dict[str, CircuitState] = {}
        self._lock = Lock()
        self.failure_threshold = max(1, int(failure_threshold))
        self.recovery_seconds = max(1, int(recovery_seconds))

    def _state_for(self, key: str) -> CircuitState:
        return self._states.setdefault(key, CircuitState())

    def allow_request(self, key: str) -> bool:
        s = self._state_for(key)
        if s.open_until is None:
            return True
        if time.time() >= s.open_until:
            # half-open: allow a trial request
            s.open_until = None
            s.failures = 0
            return True
        return False

    def record_success(self, key: str) -> None:
        s = self._state_for(key)
        s.failures = 0
        s.last_failure_at = None
        s.open_until = None

    def record_failure(self, key: str) -> None:
        s = self._state_for(key)
        s.failures += 1
        s.last_failure_at = time.time()
        if s.failures >= self.failure_threshold:
            s.open_until = time.time() + self.recovery_seconds


CircuitBreakerSingleton = CircuitBreaker()
