from __future__ import annotations

from typing import Any, Dict


class Scorecard:
    """Simple per-tenant scorecard tracking protocol enforcement metrics."""

    def __init__(self) -> None:
        self._cards: Dict[str, Dict[str, Any]] = {}

    def _ensure(self, tenant_id: str) -> Dict[str, Any]:
        return self._cards.setdefault(
            tenant_id,
            {
                "signature_total": 0,
                "signature_asymmetric": 0,
                "sandbox_pass": 0,
                "approvals_required": 0,
                "rollbacks": 0,
            },
        )

    def record_signature(self, tenant_id: str, asymmetric: bool = False) -> None:
        c = self._ensure(tenant_id)
        c["signature_total"] += 1
        if asymmetric:
            c["signature_asymmetric"] += 1

    def record_sandbox(self, tenant_id: str, passed: bool = True) -> None:
        c = self._ensure(tenant_id)
        if passed:
            c["sandbox_pass"] += 1

    def record_approval(self, tenant_id: str, required: bool = True) -> None:
        c = self._ensure(tenant_id)
        if required:
            c["approvals_required"] += 1

    def record_rollback(self, tenant_id: str) -> None:
        c = self._ensure(tenant_id)
        c["rollbacks"] += 1

    def snapshot(self, tenant_id: str) -> Dict[str, Any]:
        return dict(self._ensure(tenant_id))


ScorecardSingleton = Scorecard()
