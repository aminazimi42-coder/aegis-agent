import unittest

from core.commitment_engine import CommitmentEngineSingleton
from core.evidence_ledger import EvidenceLedgerSingleton
from core.planner import PlannerSingleton


class Phase31PlannerTests(unittest.TestCase):
    def test_planner_add_assign_and_commit(self):
        tenant = "tenant31"
        # add tasks
        t1 = PlannerSingleton.add_task(tenant, "do important work", priority=10)
        PlannerSingleton.add_task(tenant, "low priority", priority=100)
        # next task should be t1
        nxt = PlannerSingleton.get_next_task(tenant)
        self.assertEqual(nxt.task_id, t1.task_id)
        # assign task
        ok = PlannerSingleton.assign_task(t1.task_id, "worker1")
        self.assertTrue(ok)
        # create commitment
        c = CommitmentEngineSingleton.create_commitment(tenant, t1.task_id, "worker1")
        self.assertIsNotNone(c.commitment_id)
        # fulfill commitment
        f = CommitmentEngineSingleton.fulfill_commitment(c.commitment_id)
        self.assertTrue(f)
        # ledger should have entries
        snap = EvidenceLedgerSingleton.snapshot()
        self.assertGreaterEqual(snap["count"], 1)


if __name__ == "__main__":
    unittest.main()
