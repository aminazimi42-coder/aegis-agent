import unittest

from core.cognitive_identity import CognitiveIdentitySingleton
from core.evidence_ledger import EvidenceLedgerSingleton
from core.knowledge_graph import KnowledgeGraphSingleton


class Phase29Tests(unittest.TestCase):
    def test_identity_enroll_and_resolve(self):
        tenant = "tenant29"
        alice = CognitiveIdentitySingleton.enroll(
            tenant, "alice", {"email": "a@x.com", "name": "Alice"}
        )
        bob = CognitiveIdentitySingleton.enroll(
            tenant, "bob", {"email": "b@x.com", "name": "Bob"}
        )
        # same attrs -> different fingerprints
        self.assertIsNotNone(alice.fingerprint)
        self.assertIsNotNone(bob.fingerprint)
        self.assertNotEqual(alice.fingerprint, bob.fingerprint)
        # link alice and bob should succeed only if both enrolled
        ok = CognitiveIdentitySingleton.link(tenant, "alice", "bob")
        self.assertTrue(ok)

    def test_knowledge_graph_ops(self):
        kg = KnowledgeGraphSingleton
        kg.add_node("n1", "Person", {"name": "Alice"})
        kg.add_node("n2", "Person", {"name": "Bob"})
        kg.add_edge("n1", "knows", "n2")
        neigh = kg.neighbors("n1")
        self.assertEqual(len(neigh), 1)
        self.assertEqual(neigh[0][0], "knows")
        # ledger has recorded node/edge events
        snap = EvidenceLedgerSingleton.snapshot()
        self.assertGreaterEqual(snap["count"], 1)


if __name__ == "__main__":
    unittest.main()
