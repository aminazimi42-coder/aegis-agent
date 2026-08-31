from __future__ import annotations

import time
from threading import Lock
from typing import Any


class FinOpsAutopilot:
    """Track spend, enforce per-request and tenant budgets, and block runaway
    agent workloads.
    """

    def __init__(
        self,
        tenant_daily_budget_tokens: int = 100000,
        daily_budget_cost_usd: float = 100.0,
        per_request_token_cap: int = 256,
        cost_per_1k_tokens: float = 0.01,
        default_tenant_id: str = "default",
    ) -> None:
        self.tenant_daily_budget_tokens = max(1, int(tenant_daily_budget_tokens))
        self.daily_budget_cost_usd = float(daily_budget_cost_usd)
        self.per_request_token_cap = max(1, int(per_request_token_cap))
        self.cost_per_1k_tokens = float(cost_per_1k_tokens)
        self.default_tenant_id = default_tenant_id
        self._lock = Lock()
        self._tenant_usage: dict[str, dict[str, Any]] = {}

    def _tenant_key(self, tenant_id: str | None) -> str:
        tenant = str(tenant_id or self.default_tenant_id).strip() or self.default_tenant_id
        return tenant

    def _ensure_state(self, tenant_id: str | None) -> dict[str, Any]:
        tenant_key = self._tenant_key(tenant_id)
        state = self._tenant_usage.setdefault(
            tenant_key,
            {
                "tenant_id": tenant_key,
                "total_tokens_used": 0,
                "total_cost_usd": 0.0,
                "request_count": 0,
                "last_updated": time.time(),
                "remaining_tokens": self.tenant_daily_budget_tokens,
            },
        )
        state["remaining_tokens"] = max(
            self.tenant_daily_budget_tokens - state["total_tokens_used"],
            0,
        )
        return state

    def estimate_tokens(self, task_text: str | None) -> int:
        if task_text is None:
            return 0
        cleaned = " ".join(str(task_text).strip().split())
        if not cleaned:
            return 0
        return max(1, len(cleaned) // 4)

    def estimate_cost(self, tokens_used: int) -> float:
        return round((max(0, int(tokens_used)) / 1000.0) * self.cost_per_1k_tokens, 6)

    def enforce_budget(
        self,
        tenant_id: str | None,
        task_text: str,
        estimated_tokens: int | None = None,
        estimated_cost: float | None = None,
    ) -> dict[str, Any]:
        tenant_key = self._tenant_key(tenant_id)
        if estimated_tokens is None:
            token_count = self.estimate_tokens(task_text)
        else:
            token_count = max(0, int(estimated_tokens))
        if estimated_cost is None:
            cost_estimate = self.estimate_cost(token_count)
        else:
            cost_estimate = float(estimated_cost)

        with self._lock:
            state = self._ensure_state(tenant_key)
            if token_count > self.per_request_token_cap:
                raise RuntimeError(
                    "Token request for tenant '%s' exceeds the hard request cap "
                    "of %s."
                    % (tenant_key, self.per_request_token_cap)
                )
            if state["total_tokens_used"] + token_count > self.tenant_daily_budget_tokens:
                raise RuntimeError(
                    "Tenant '%s' exceeded the daily token budget. Request blocked."
                    % tenant_key
                )
            if state["total_cost_usd"] + cost_estimate > self.daily_budget_cost_usd:
                raise RuntimeError(
                    "Tenant '%s' exceeded the daily cost budget. Request blocked."
                    % tenant_key
                )

            state["last_updated"] = time.time()
            state["remaining_tokens"] = max(
                self.tenant_daily_budget_tokens - state["total_tokens_used"],
                0,
            )
            return {
                "tenant_id": tenant_key,
                "estimated_tokens": token_count,
                "estimated_cost_usd": round(cost_estimate, 6),
                "remaining_tokens": state["remaining_tokens"],
            }

    def record_usage(
        self,
        tenant_id: str | None,
        task_text: str,
        agent_name: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> dict[str, Any]:
        token_count = self.estimate_tokens(task_text)
        if prompt_tokens is not None:
            token_count = max(token_count, int(prompt_tokens))
        if completion_tokens is not None:
            token_count = max(token_count, int(prompt_tokens or 0) + int(completion_tokens))

        cost_estimate = self.estimate_cost(token_count)
        tenant_key = self._tenant_key(tenant_id)

        with self._lock:
            state = self._ensure_state(tenant_key)
            state["total_tokens_used"] += token_count
            state["total_cost_usd"] = round(state["total_cost_usd"] + cost_estimate, 6)
            state["request_count"] += 1
            state["last_updated"] = time.time()
            state["remaining_tokens"] = max(
                self.tenant_daily_budget_tokens - state["total_tokens_used"],
                0,
            )
            return {
                "tenant_id": tenant_key,
                "agent_name": agent_name,
                "tokens_used": token_count,
                "cost_usd": round(cost_estimate, 6),
                "total_tokens_used": state["total_tokens_used"],
                "total_cost_usd": round(state["total_cost_usd"], 6),
                "remaining_tokens": state["remaining_tokens"],
                "request_count": state["request_count"],
            }

    def snapshot(self, tenant_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if tenant_id is not None:
                state = self._tenant_usage.get(self._tenant_key(tenant_id))
                if state is None:
                    state = self._ensure_state(tenant_id)
                return {
                    "tenant_id": state["tenant_id"],
                    "total_tokens_used": state["total_tokens_used"],
                    "total_cost_usd": round(state["total_cost_usd"], 6),
                    "request_count": state["request_count"],
                    "remaining_tokens": state["remaining_tokens"],
                }
            serialized = {}
            for tenant_key, state in self._tenant_usage.items():
                serialized[tenant_key] = {
                    "tenant_id": state["tenant_id"],
                    "total_tokens_used": state["total_tokens_used"],
                    "total_cost_usd": round(state["total_cost_usd"], 6),
                    "request_count": state["request_count"],
                    "remaining_tokens": state["remaining_tokens"],
                }
            return serialized
