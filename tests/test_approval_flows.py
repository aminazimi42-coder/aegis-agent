from __future__ import annotations

import unittest

from app.server import app
from core.evidence_ledger import EvidenceLedgerSingleton
from fastapi.testclient import TestClient


class TestApprovalFlows(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        # clear ledger entries for deterministic assertions
        EvidenceLedgerSingleton.remove_last(9999)

    def test_request_and_decide_approval(self):
        # request approval
        resp = self.client.post(
            "/approvals/request",
            json={"action": "install_capsule", "tenant_id": "t1", "requester": "tester"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        appr_id = data["approval_id"]
        self.assertIn("status", data)

        # ensure ledger recorded the request
        entries = EvidenceLedgerSingleton.entries()
        self.assertTrue(any(e["action"] == "approval_requested" for e in entries))

        # decide approval
        resp2 = self.client.post(
            f"/approvals/{appr_id}/decide",
            json={"decision": "approve", "approver": "admin"},
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data2.get("decision"), "approve")

        # ledger should include decision
        entries2 = EvidenceLedgerSingleton.entries()
        self.assertTrue(any(e["action"] == "approval_decision" for e in entries2))


if __name__ == "__main__":
    unittest.main()
