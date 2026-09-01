from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class UsageRecord:
    tokens: int = 0
    calls: int = 0
    models: Dict[str, int] = field(default_factory=dict)


class UsageMeter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: Dict[str, UsageRecord] = {}

    def record_usage(
        self,
        tenant_id: str,
        tokens: int,
        model: str,
        operation: str = "inference",
    ) -> None:
        with self._lock:
            r = self._data.setdefault(tenant_id, UsageRecord())
            r.tokens += int(tokens)
            r.calls += 1
            r.models[model] = r.models.get(model, 0) + int(tokens)

    def get_usage(self, tenant_id: str) -> UsageRecord:
        with self._lock:
            return self._data.get(tenant_id, UsageRecord())


# Singleton instance for simple global access in the codebase
UsageMeterSingleton = UsageMeter()
