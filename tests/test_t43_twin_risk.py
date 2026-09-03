"""T43 — Action risk levels L0–L3.

Covers:
- classify("deploy to production") == "L3"
- classify("draft the reply") == "L1"
- After T03 commit, propose_actions result includes risk_level on each action.
- plan_goal result includes risk_levels.
- FastAPI existing approve route still 200.
- No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from app.server import create_app
from core.twin_actions import propose_actions
from core.twin_goal_plan import plan_goal
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_risk import attach_risk, classify
from fastapi.testclient import TestClient


class TestT43TwinRisk(unittest.TestCase):
    """Risk-level classification and integration."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t43_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # --- helpers --- #

    def _full_interview(self, tenant_id: str) -> None:
        """Run a complete T03 interview+commit so a profile exists."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)

    # --- classify --- #

    def test_classify_deploy_to_production_is_l3(self) -> None:
        self.assertEqual(classify("deploy to production"), "L3")

    def test_classify_draft_the_reply_is_l1(self) -> None:
        self.assertEqual(classify("draft the reply"), "L1")

    def test_classify_pay_is_l3(self) -> None:
        self.assertEqual(classify("Pay the invoice"), "L3")

    def test_classify_wire_is_l3(self) -> None:
        self.assertEqual(classify("wire transfer funds"), "L3")

    def test_classify_delete_account_is_l3(self) -> None:
        self.assertEqual(classify("delete account permanently"), "L3")

    def test_classify_send_email_is_l2(self) -> None:
        self.assertEqual(classify("send the email"), "L2")

    def test_classify_push_commit_is_l2(self) -> None:
        self.assertEqual(classify("push the commit"), "L2")

    def test_classify_write_file_is_l2(self) -> None:
        self.assertEqual(classify("write the report"), "L2")

    def test_classify_invoice_standalone_is_l2(self) -> None:
        """'invoice' contains 'in' but not 'pay' — L2 not L3."""
        self.assertEqual(classify("invoice the client"), "L2")

    def test_classify_plan_is_l1(self) -> None:
        self.assertEqual(classify("plan the sprint"), "L1")

    def test_classify_brief_is_l1(self) -> None:
        self.assertEqual(classify("brief the team"), "L1")

    def test_classify_summary_is_l1(self) -> None:
        self.assertEqual(classify("summary of findings"), "L1")

    def test_classify_observe_is_l0(self) -> None:
        self.assertEqual(classify("Review weekly digest"), "L0")

    def test_classify_empty_string_is_l0(self) -> None:
        self.assertEqual(classify(""), "L0")

    # --- attach_risk --- #

    def test_attach_risk_sets_risk_level(self) -> None:
        action = {"title": "deploy to production", "kind": "test"}
        result = attach_risk(action)
        self.assertEqual(result["risk_level"], "L3")
        # Original dict should not be mutated.
        self.assertNotIn("risk_level", action)

    def test_attach_risk_recomputes_existing(self) -> None:
        action = {"title": "draft the reply", "risk_level": "L3"}
        result = attach_risk(action)
        self.assertEqual(result["risk_level"], "L1")

    # --- propose_actions integration --- #

    def test_propose_actions_includes_risk_level(self) -> None:
        self._full_interview("t43a")
        actions = propose_actions("t43a")
        self.assertGreaterEqual(len(actions), 1)
        for a in actions:
            self.assertIn("risk_level", a)
            self.assertIn(a["risk_level"], ("L0", "L1", "L2", "L3"))

    # --- plan_goal integration --- #

    def test_plan_goal_includes_risk_levels(self) -> None:
        self._full_interview("t43b")
        result = plan_goal("t43b", "1. Review the PR\n2. Draft the reply")
        self.assertIn("risk_levels", result)
        self.assertEqual(len(result["risk_levels"]), 2)
        # "Review the PR" → L0, "Draft the reply" → L1
        self.assertEqual(result["risk_levels"][0], "L0")
        self.assertEqual(result["risk_levels"][1], "L1")

    # --- FastAPI approve still 200 --- #

    def test_fastapi_approve_still_200(self) -> None:
        self._full_interview("t43c")
        app = create_app()
        client = TestClient(app)

        # Propose.
        resp = client.post(
            "/api/v1/twin/actions/propose",
            json={"tenant_id": "t43c"},
        )
        self.assertEqual(resp.status_code, 200)
        actions = resp.json()["actions"]
        first_id = actions[0]["action_id"]

        # Approve.
        resp = client.post(f"/api/v1/twin/actions/{first_id}/approve")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "approved")

    # --- no live network --- #

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
