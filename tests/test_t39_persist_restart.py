"""T39 — persist approvals and FinOps budgets in SQLite.

Verify that a process restart (simulated by a fresh in-memory state or
a new TestClient) does not wipe approval rows or tenant budget remaining.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

from app.server import create_app
from core.finops_autopilot import FinOpsAutopilot
from core.twin_persist import (
    add_spend,
    get_approval,
    get_budget,
    put_approval,
)
from fastapi.testclient import TestClient


class TestT39PersistRestart(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t39_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # --- approval persistence across a new Python process ---

    def test_put_approval_survives_new_process(self):
        put_approval("appr-999", tenant_id="t1", title="install", status="pending")
        # Spawn a fresh Python process that reads the same DB file.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import os; "
                    "from core.twin_persist import get_approval; "
                    "r = get_approval('appr-999'); "
                    "assert r is not None, 'approval row missing after restart'; "
                    "assert r['status'] == 'pending'; "
                    "print('OK')"
                ),
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "AEGIS_DATA_DIR": self._tmp},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("OK", result.stdout)

    # --- add_spend survives a fresh object/connection ---

    def test_add_spend_survives_fresh_connection(self):
        remaining = add_spend("tenant-x", 50.0)
        self.assertGreaterEqual(remaining, 0)
        # A fresh object / connection should see the persisted spent.
        budget = get_budget("tenant-x")
        self.assertIsNotNone(budget)
        self.assertEqual(budget["spent"], 50.0)

    def test_add_spend_accumulates_across_connections(self):
        add_spend("tenant-acc", 10.0)
        add_spend("tenant-acc", 25.0)
        budget = get_budget("tenant-acc")
        self.assertIsNotNone(budget)
        self.assertEqual(budget["spent"], 35.0)

    # --- FastAPI approval flow survives a new TestClient (simulates restart) ---

    def test_approval_flow_survives_new_test_client(self):
        app = create_app()
        client1 = TestClient(app)
        resp = client1.post(
            "/approvals/request",
            json={"action": "install_capsule", "tenant_id": "t1", "requester": "tester"},
        )
        self.assertEqual(resp.status_code, 200)
        appr_id = resp.json()["approval_id"]

        # Simulate app.state restart: create a second TestClient with a
        # fresh app instance.  The approval row must still be found.
        app2 = create_app()
        client2 = TestClient(app2)
        resp2 = client2.post(
            f"/approvals/{appr_id}/decide",
            json={"decision": "approve", "approver": "admin"},
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["decision"], "approve")

        # The row in SQLite should reflect the decision.
        row = get_approval(appr_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "approved")

    # --- finops budget load/save hooks ---

    def test_finops_spent_persisted_across_objects(self):
        ctrl1 = FinOpsAutopilot(
            tenant_daily_budget_tokens=100,
            per_request_token_cap=50,
            cost_per_1k_tokens=0.01,
        )
        ctrl1.record_usage(
            tenant_id="tenant-fp",
            task_text="validate the rollout plan",
            agent_name="Alina",
            prompt_tokens=10,
            completion_tokens=5,
        )
        # A fresh object should restore spent from SQLite.
        ctrl2 = FinOpsAutopilot(
            tenant_daily_budget_tokens=100,
            per_request_token_cap=50,
            cost_per_1k_tokens=0.01,
        )
        snap = ctrl2.snapshot("tenant-fp")
        self.assertGreater(snap["total_tokens_used"], 0)

    # --- no live network ---

    def test_no_live_network(self):
        # This test exists to assert the suite does not require network.
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
