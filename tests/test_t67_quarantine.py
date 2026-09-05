"""T67 — Quarantine non-core product scaffolds.

Asserts that marketplace, sandbox, omnichannel, desktop_engine, and KG stubs
are flagged QUARANTINED and cannot be mistaken for live product paths.
"""
import unittest

import core.capsule_marketplace as capsule_marketplace
import core.desktop_engine as desktop_engine
import core.knowledge_graph as knowledge_graph
import core.marketplace_sync as marketplace_sync
import core.omnichannel as omnichannel
import core.runtime_sandbox as runtime_sandbox
import core.sandbox as sandbox
from core.omnichannel import BridgeManager, EmailBridge, SlackBridge


class TestT67Quarantine(unittest.TestCase):
    def test_all_modules_quarantined(self):
        self.assertIs(capsule_marketplace.QUARANTINED, True)
        self.assertIs(marketplace_sync.QUARANTINED, True)
        self.assertIs(runtime_sandbox.QUARANTINED, True)
        self.assertIs(sandbox.QUARANTINED, True)
        self.assertIs(omnichannel.QUARANTINED, True)
        self.assertIs(desktop_engine.QUARANTINED, True)
        self.assertIs(knowledge_graph.QUARANTINED, True)

    def test_omnichannel_send_cannot_succeed_live(self):
        mgr = BridgeManager()
        mgr.register("slack", SlackBridge())
        mgr.register("email", EmailBridge())
        # Slack and Email bridges must raise RuntimeError("quarantined")
        with self.assertRaises(RuntimeError):
            mgr.send("slack", "t", "#general", "hi")
        with self.assertRaises(RuntimeError):
            mgr.send("email", "t", "a@example.com", "hi")

    def test_no_live_network(self):
        # Ensure no live SMTP / webhook attributes are wired
        for name in ("slack", "email"):
            bridge = SlackBridge() if name == "slack" else EmailBridge()
            self.assertFalse(hasattr(bridge, "_smtp"))
            self.assertFalse(hasattr(bridge, "_webhook"))


if __name__ == "__main__":
    unittest.main()
