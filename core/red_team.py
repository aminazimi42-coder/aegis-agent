from __future__ import annotations

from typing import Callable, List

from .evidence_ledger import EvidenceLedgerSingleton


class RedTeam:
    """Run simulated adversarial tests against a provided target function.

    Each test is a callable that must return a dict with `ok` (bool) and `details`.
    Results are appended to the evidence ledger for post-mortem and audit.
    """

    def __init__(self) -> None:
        self.tests: List[Callable[[], dict]] = []

    def register(self, test_fn: Callable[[], dict]) -> None:
        self.tests.append(test_fn)

    def run(self, tenant_id: str) -> List[dict]:
        results: List[dict] = []
        for t in self.tests:
            try:
                r = t()
            except Exception as exc:
                r = {"ok": False, "details": str(exc)}
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor="red_team",
                action="test_result",
                payload={"result": r},
            )
            results.append(r)
        return results


DefaultRedTeam = RedTeam()
