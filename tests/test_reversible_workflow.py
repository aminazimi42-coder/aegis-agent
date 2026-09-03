import os
import tempfile
import unittest

from core.evidence_ledger import EvidenceLedger
from core.reversible_workflow import ReversibleWorkflowManager
from core.tenant_memory import TenantMemoryVault


class ReversibleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self):
        del os.environ["AEGIS_DATA_DIR"]

    def test_rollback_deletes_memory_and_ledger(self):
        ledger = EvidenceLedger()
        tenant_memory = TenantMemoryVault()
        mgr = ReversibleWorkflowManager()

        mgr.begin()
        # store memory and register rollback
        tenant_memory.store(tenant_id="t1", key="k1", value={"v": 1}, namespace="ns")
        mgr.execute(lambda: None, lambda: tenant_memory.delete("t1", "k1", namespace="ns"))
        # append ledger entry and register rollback
        ledger.append_entry(tenant_id="t1", actor="a1", action="act", payload={"v": 1})
        mgr.execute(lambda: None, lambda: ledger.remove_last(1))

        # simulate failure -> rollback
        mgr.rollback()

        # memory should be gone
        with self.assertRaises(KeyError):
            tenant_memory.read("t1", "k1", namespace="ns")

        # ledger should have zero entries
        self.assertEqual(len(ledger.entries()), 0)


if __name__ == "__main__":
    unittest.main()
