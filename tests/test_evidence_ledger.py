import unittest

from core.evidence_ledger import EvidenceLedger


class EvidenceLedgerTests(unittest.TestCase):
    def test_append_and_verify_chain(self):
        ledger = EvidenceLedger()
        _ = ledger.append_entry(tenant_id="t1", actor="a1", action="create", payload={"v": 1})
        _ = ledger.append_entry(tenant_id="t1", actor="a2", action="update", payload={"v": 2})
        self.assertEqual(len(ledger.entries()), 2)
        self.assertTrue(ledger.verify_chain())

    def test_tamper_detection(self):
        ledger = EvidenceLedger()
        ledger.append_entry(tenant_id="t1", actor="a1", action="create", payload={"v": 1})
        ledger.append_entry(tenant_id="t1", actor="a2", action="update", payload={"v": 2})
        # tamper with payload
        ledger._entries[1].payload["v"] = 999
        self.assertFalse(ledger.verify_chain())
        bad = ledger.find_tamper_indices()
        self.assertTrue(len(bad) >= 1)


if __name__ == "__main__":
    unittest.main()
