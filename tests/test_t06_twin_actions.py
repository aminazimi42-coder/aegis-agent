"""T06 — Twin proposed actions with human approval gate.

Covers:
- propose_actions without a consented profile raises ValueError.
- After a T03 interview+commit, propose_actions returns >= 1 proposed action.
- execute before approve raises PermissionError.
- approve then execute -> status executed.
- FastAPI: propose 200, approve 200, execute 200.
- AEGIS_DATA_DIR temp isolation; no network.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from app.server import create_app
from core.twin_actions import (
    _action_digest,
    _load_action,
    approve,
    execute,
    list_actions,
    propose_actions,
    reject,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT06TwinActions(unittest.TestCase):
    """Proposed twin actions with human approval gate."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> None:
        """Run a complete T03 interview+commit so a profile exists."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_propose_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            propose_actions("no_profile_t6")

    def test_propose_after_interview_returns_proposed(self) -> None:
        self._full_interview("t6a")
        actions = propose_actions("t6a")
        self.assertGreaterEqual(len(actions), 1)
        for a in actions:
            self.assertEqual(a["status"], "proposed")
            self.assertEqual(a["tenant_id"], "t6a")
            self.assertIn(a["kind"], ("review_digest", "review_repos", "prepare_weekly_plan"))

    def test_execute_before_approve_raises_permission_error(self) -> None:
        self._full_interview("t6b")
        actions = propose_actions("t6b")
        first_id = actions[0]["action_id"]
        with self.assertRaises(PermissionError):
            execute(first_id, "t6b")

    def test_approve_then_execute_status_executed(self) -> None:
        self._full_interview("t6c")
        actions = propose_actions("t6c")
        first_id = actions[0]["action_id"]

        _action = _load_action(first_id)
        assert _action is not None
        approved = approve(first_id, "t6c", "tester", _action_digest(_action))
        self.assertEqual(approved["status"], "approved")

        executed = execute(first_id, "t6c")
        self.assertEqual(executed["status"], "executed")

    def test_reject_sets_status_rejected(self) -> None:
        self._full_interview("t6d")
        actions = propose_actions("t6d")
        first_id = actions[0]["action_id"]
        rejected = reject(first_id, "t6d")
        self.assertEqual(rejected["status"], "rejected")

    def test_unknown_action_id_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            approve("nonexistent-id", "t6x", "tester", "deadbeef")
        with self.assertRaises(ValueError):
            reject("nonexistent-id")
        with self.assertRaises(ValueError):
            execute("nonexistent-id")

    def test_list_actions_returns_all_for_tenant(self) -> None:
        self._full_interview("t6e")
        propose_actions("t6e")
        actions = list_actions("t6e")
        self.assertGreaterEqual(len(actions), 1)
        for a in actions:
            self.assertEqual(a["tenant_id"], "t6e")

    def test_list_actions_empty_for_unknown_tenant(self) -> None:
        actions = list_actions("never_exists")
        self.assertEqual(len(actions), 0)

    # ------------------------------------------------------------------ #
    # FastAPI
    # ------------------------------------------------------------------ #

    def test_fastapi_propose_approve_execute_200(self) -> None:
        self._full_interview("t6f")
        app = create_app()
        client = TestClient(app)

        # Propose.
        resp = client.post(
            "/api/v1/twin/actions/propose",
            json={"tenant_id": "t6f"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(body["count"], 1)
        first_id = body["actions"][0]["action_id"]

        # Approve.
        from core.twin_actions import _action_digest as _digest
        from core.twin_actions import _load_action as _load

        _a = _load(first_id)
        assert _a is not None
        resp = client.post(
            f"/api/v1/twin/actions/{first_id}/approve",
            json={
                "tenant_id": "t6f",
                "actor_id": "tester",
                "expected_payload_sha256": _digest(_a),
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "approved")

        # Execute.
        resp = client.post(
            f"/api/v1/twin/actions/{first_id}/execute",
            json={"tenant_id": "t6f"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "executed")

    def test_fastapi_propose_without_profile_400(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/actions/propose",
            json={"tenant_id": "no_profile_t6"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_fastapi_execute_before_approve_403(self) -> None:
        self._full_interview("t6g")
        app = create_app()
        client = TestClient(app)

        resp = client.post(
            "/api/v1/twin/actions/propose",
            json={"tenant_id": "t6g"},
        )
        self.assertEqual(resp.status_code, 200)
        first_id = resp.json()["actions"][0]["action_id"]

        resp = client.post(
            f"/api/v1/twin/actions/{first_id}/execute",
            json={"tenant_id": "t6g"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_fastapi_get_actions_list(self) -> None:
        self._full_interview("t6h")
        app = create_app()
        client = TestClient(app)

        client.post(
            "/api/v1/twin/actions/propose",
            json={"tenant_id": "t6h"},
        )

        resp = client.get("/api/v1/twin/actions/t6h")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(body["count"], 1)


if __name__ == "__main__":
    unittest.main()
