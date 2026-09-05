import unittest

from core.data_governance import ConsentStoreSingleton, PolicyEngineSingleton
from core.evidence_ledger import EvidenceLedgerSingleton
from core.marketplace_sync import MarketplaceSyncSingleton
from core.omnichannel import BridgeManagerSingleton, EmailBridge, SlackBridge


class Phase26GovernanceTests(unittest.TestCase):
    def test_consent_and_policy(self):
        tenant = "tenant26"
        subject = "user123"
        # policy allow data:profile
        PolicyEngineSingleton.add_allow("data:profile")
        ConsentStoreSingleton.grant(tenant, subject, ["data:profile"])
        allowed = ConsentStoreSingleton.check(tenant, subject, ["data:profile"])
        self.assertTrue(allowed)

    def test_omnichannel_and_marketplace(self):
        tenant = "tenant26"
        # register bridges — quarantined: send must not succeed as live
        BridgeManagerSingleton.register("slack", SlackBridge())
        BridgeManagerSingleton.register("email", EmailBridge())
        with self.assertRaises(RuntimeError):
            BridgeManagerSingleton.send("slack", tenant, "#general", "hello")
        with self.assertRaises(RuntimeError):
            BridgeManagerSingleton.send("email", tenant, "a@example.com", "hello")
        # marketplace register
        MarketplaceSyncSingleton.register_capsule(tenant, "capsule-1", {"name": "capsule"})
        caps = MarketplaceSyncSingleton.list_capsules()
        self.assertIn("capsule-1", caps)
        # ledger should have entries for these actions
        snap = EvidenceLedgerSingleton.snapshot()
        self.assertGreaterEqual(snap["count"], 1)


if __name__ == "__main__":
    unittest.main()
