from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Any


class TokenOptimizer:
    """Track request token consumption, cache repeated responses, and enforce budgets."""

    def __init__(
        self,
        max_tokens_per_request: int = 4000,
        daily_budget: int = 100000,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.max_tokens_per_request = max_tokens_per_request
        self.daily_budget = daily_budget
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, dict[str, Any]] = {}
        self._request_history: list[dict[str, Any]] = []
        self._lock = Lock()
        self._total_tokens = 0
        self._recent_requests: dict[str, list[float]] = defaultdict(list)

    def _normalize_task(self, task: str) -> str:
        return " ".join(task.strip().split()).lower()

    def estimate_tokens(self, text: str | None) -> int:
        if text is None:
            return 0
        return max(1, len(text) // 4)

    def cache_response(self, task: str, agent_name: str, response: str) -> bool:
        key = self._normalize_task(task)
        now = time.time()
        with self._lock:
            self._cache[key] = {
                "task": task,
                "agent_name": agent_name,
                "response": response,
                "timestamp": now,
                "expires_at": now + self.cache_ttl_seconds,
            }
            return True

    def get_cached_response(self, task: str) -> str | None:
        key = self._normalize_task(task)
        now = time.time()
        with self._lock:
            cached = self._cache.get(key)
            if cached is None:
                return None
            if now > cached["expires_at"]:
                self._cache.pop(key, None)
                return None
            return cached["response"]

    def record_usage(
        self,
        task: str,
        agent_name: str,
        response: str | None = None,
    ) -> dict[str, Any]:
        task_tokens = self.estimate_tokens(task)
        response_tokens = self.estimate_tokens(response)
        total_tokens = task_tokens + response_tokens

        with self._lock:
            if total_tokens > self.max_tokens_per_request:
                total_tokens = self.max_tokens_per_request

            self._total_tokens += total_tokens
            entry = {
                "task": task,
                "agent_name": agent_name,
                "tokens_used": total_tokens,
                "timestamp": time.time(),
            }
            self._request_history.append(entry)
            self._recent_requests[agent_name].append(time.time())
            self._recent_requests[agent_name] = [
                ts for ts in self._recent_requests[agent_name] if time.time() - ts <= 60
            ]

        self.cache_response(task, agent_name, response or "")
        return {
            "task": task,
            "agent_name": agent_name,
            "tokens_used": total_tokens,
            "total_tokens": self._total_tokens,
            "daily_budget_remaining": max(self.daily_budget - self._total_tokens, 0),
        }

    def usage_summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_tokens": self._total_tokens,
                "daily_budget": self.daily_budget,
                "remaining_tokens": max(self.daily_budget - self._total_tokens, 0),
                "cache_entries": len(self._cache),
                "request_count": len(self._request_history),
            }

    def enforce_budget(self) -> None:
        if self._total_tokens >= self.daily_budget:
            raise RuntimeError("Daily token budget exceeded. Throttling agent execution.")

    def throttle_if_needed(self, agent_name: str, max_requests_per_minute: int = 30) -> bool:
        window = self._recent_requests.get(agent_name, [])
        if len(window) >= max_requests_per_minute:
            return True
        return False
