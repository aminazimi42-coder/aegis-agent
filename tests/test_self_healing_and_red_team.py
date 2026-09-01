from __future__ import annotations

import unittest

from core.evidence_ledger import EvidenceLedgerSingleton
from core.red_team import DefaultRedTeam
from core.self_healing import SelfHealingPipeline


class TestSelfHealingAndRedTeam(unittest.TestCase):
    def setUp(self) -> None:
        EvidenceLedgerSingleton.remove_last(9999)

    def test_self_healing_success_and_failure(self):
        # success steps
        steps = [lambda: True, lambda: True]
        ok = SelfHealingPipeline(retries=1).run("t-sh", steps)
        self.assertTrue(ok)

        # failing step after retries
        counter = {"n": 0}

        def flaky():
            counter["n"] += 1
            if counter["n"] < 3:
                raise RuntimeError("transient")
            return True

        ok2 = SelfHealingPipeline(retries=1, backoff_seconds=0).run("t-sh", [flaky])
        self.assertFalse(ok2)

    def test_red_team_records(self):
        def sample_test():
            return {"ok": True, "details": "probe passed"}

        DefaultRedTeam.register(sample_test)
        results = DefaultRedTeam.run("t-red")
        self.assertEqual(len(results), 1)
        entries = EvidenceLedgerSingleton.entries()
        self.assertTrue(any(e["action"] == "test_result" for e in entries))


if __name__ == "__main__":
    unittest.main()
