from __future__ import annotations

import unittest

from core.circuit_breaker import CircuitBreakerSingleton
from core.evidence_ledger import EvidenceLedgerSingleton
from core.model_router import TrustAwareModelRouter


class TestModelResilience(unittest.TestCase):
    def setUp(self) -> None:
        # clear ledger and breaker state
        EvidenceLedgerSingleton.remove_last(9999)
        # reset circuit breaker internal states
        CircuitBreakerSingleton._states.clear()

    def test_fallback_on_failure(self):
        router = TrustAwareModelRouter(max_retries=0)

        # Monkeypatch AICore.dispatch to raise on first call, then return a minimal payload
        import core.ai_core as ai_core_module

        original_dispatch = ai_core_module.AICore.dispatch

        call_count = {"n": 0}

        def fake_dispatch(self, task: str):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated model failure")
            return original_dispatch(self, task)

        ai_core_module.AICore.dispatch = fake_dispatch  # type: ignore

        try:
            resp = router.route("deploy runtime optimization")
            self.assertEqual(resp.status, "completed")
            # ledger should contain a route_exception or route_failure and a route_success
            actions = [e["action"] for e in EvidenceLedgerSingleton.entries()]
            self.assertTrue(any(a in ("route_exception", "route_failure") for a in actions))
            self.assertTrue(any(a == "route_success" for a in actions))
        finally:
            ai_core_module.AICore.dispatch = original_dispatch


if __name__ == "__main__":
    unittest.main()
