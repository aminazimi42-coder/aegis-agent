from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class RetryGuard:
    """Prevent infinite retry loops with a two-retry circuit breaker."""

    def __init__(self, max_retries: int = 2) -> None:
        self.max_retries = max(0, max_retries)
        self._lock = Lock()
        self.state: dict[str, dict[str, Any]] = {}

    def _ensure_task_state(self, task_key: str) -> dict[str, Any]:
        task_state = self.state.setdefault(
            task_key,
            {
                "failures": 0,
                "status": "healthy",
                "last_error": None,
                "retry_count": 0,
                "telemetry": {
                    "attempts": 0,
                    "last_failure": None,
                    "last_success": None,
                },
            },
        )
        return task_state

    def record_success(self, task_key: str) -> dict[str, Any]:
        with self._lock:
            task_state = self._ensure_task_state(task_key)
            task_state["failures"] = 0
            task_state["status"] = "healthy"
            task_state["retry_count"] = 0
            task_state["telemetry"]["last_success"] = task_key
            return deepcopy(task_state)

    def record_failure(self, task_key: str, error: str | Exception | None = None) -> dict[str, Any]:
        with self._lock:
            task_state = self._ensure_task_state(task_key)
            task_state["failures"] += 1
            task_state["status"] = "degraded" if task_state["failures"] <= self.max_retries else "open"
            task_state["retry_count"] = task_state["failures"]
            task_state["last_error"] = str(error) if error is not None else "unknown error"
            task_state["telemetry"]["attempts"] += 1
            task_state["telemetry"]["last_failure"] = task_state["last_error"]
            return deepcopy(task_state)

    def should_retry(self, task_key: str) -> bool:
        with self._lock:
            task_state = self._ensure_task_state(task_key)
            return task_state["failures"] <= self.max_retries

    def execute(self, task_key: str, action: Callable[[], T]) -> T:
        for attempt in range(self.max_retries + 1):
            try:
                result = action()
                self.record_success(task_key)
                return result
            except Exception as exc:  # pragma: no cover - branch exercised in integration tests
                self.record_failure(task_key, exc)
                if attempt >= self.max_retries:
                    self.state[task_key]["status"] = "open"
                    raise RuntimeError(
                        f"Retry budget exceeded for task '{task_key}' after {self.max_retries} retries."
                    ) from exc
        raise RuntimeError(f"Execution halted for task '{task_key}' due to retry limits.")

    def snapshot(self, task_key: str | None = None) -> dict[str, Any]:
        with self._lock:
            if task_key is None:
                return deepcopy(self.state)
            return deepcopy(self.state.get(task_key, {}))
