"""T01 Platform Integrity tests.

Asserts that:
- AGENT_REGISTRY has exactly six agents in the correct order.
- AICore routes security/KMS tasks to Ahmad and finance/invoice to Amin.
- run_workflow produces six results.
- SecurityPolicy allow-list includes "Ahmad" (not "Ahmed").
- AppConfig defaults to agent_count=6 and version=1.0.0-rc1.
- EvidenceLedger persists to SQLite and a new instance sees prior entries.
- TaskStore persists to SQLite and a new instance sees prior tasks.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from core.agent_registry import AGENT_REGISTRY
from core.ai_core import AICore
from core.config import load_config
from core.evidence_ledger import EvidenceLedger
from core.security import SecurityPolicy
from core.task_store import TaskStore


class TestT01PlatformIntegrity(unittest.TestCase):
    """Verify all T01 structural invariants."""

    # ---- A: Registry + runtime ----

    def test_registry_has_six_agents_in_order(self):
        names = [a.name for a in AGENT_REGISTRY]
        self.assertEqual(names, ["Alina", "Kian", "Bita", "Aylin", "Ahmad", "Amin"])

    def test_registry_ahmad_role_is_security_oversight(self):
        ahmad = next(a for a in AGENT_REGISTRY if a.name == "Ahmad")
        self.assertIn("security", ahmad.role.lower())
        self.assertIn("oversight", ahmad.role.lower())

    def test_registry_amin_role_is_finance_executive(self):
        amin = next(a for a in AGENT_REGISTRY if a.name == "Amin")
        self.assertIn("finance", amin.role.lower())

    def test_ai_core_dispatches_security_to_ahmad(self):
        core = AICore()
        result = core.dispatch("Rotate KMS keys and review the incident")
        self.assertEqual(result["agent_name"], "Ahmad")

    def test_ai_core_dispatches_finance_to_amin(self):
        core = AICore()
        result = core.dispatch("Create the invoice and settle the token budget")
        self.assertEqual(result["agent_name"], "Amin")

    def test_run_workflow_returns_six_results(self):
        core = AICore()
        results = core.run_workflow("ship the release")
        self.assertEqual(len(results), 6)

    def test_security_policy_allows_ahmad(self):
        policy = SecurityPolicy()
        self.assertTrue(policy.is_allowed("Ahmad"))
        self.assertFalse(policy.is_allowed("Ahmed"))

    # ---- B: Version SSOT ----

    def test_config_defaults_to_six_agents_and_rc1(self):
        cfg = load_config()
        self.assertEqual(cfg.agent_count, 6)
        self.assertEqual(cfg.version, "1.0.0-rc1")

    # ---- C: SQLite persistence ----

    def test_evidence_ledger_persists_across_instances(self):
        tmpdir = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = tmpdir
        try:
            ledger_a = EvidenceLedger()
            ledger_a.append_entry(
                tenant_id="t01",
                actor="test",
                action="persistence_probe",
                payload={"ok": True},
            )
            self.assertTrue(ledger_a.verify_chain())
            self.assertEqual(len(ledger_a.entries()), 1)

            # A fresh instance pointing at the same DB should see the entry.
            ledger_b = EvidenceLedger()
            self.assertEqual(len(ledger_b.entries()), 1)
            self.assertTrue(ledger_b.verify_chain())

            # remove_last should delete the DB row too.
            ledger_b.remove_last(1)
            ledger_c = EvidenceLedger()
            self.assertEqual(len(ledger_c.entries()), 0)
        finally:
            del os.environ["AEGIS_DATA_DIR"]

    def test_task_store_persists_across_instances(self):
        tmpdir = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = tmpdir
        try:
            store_a = TaskStore()
            record = store_a.get_or_create(
                "persist the release", idempotency_key="t01-persist"
            )
            self.assertEqual(record["status"], "queued")

            # A fresh instance should see the prior task.
            store_b = TaskStore()
            found = store_b.get_by_idempotency_key("t01-persist")
            self.assertIsNotNone(found)
            self.assertEqual(found["task"], "persist the release")
        finally:
            del os.environ["AEGIS_DATA_DIR"]


if __name__ == "__main__":
    unittest.main()
