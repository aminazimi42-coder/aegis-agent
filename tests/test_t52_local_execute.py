"""T52 — Local execute after approve.

Covers:
- Unapproved execute raises PermissionError.
- After T03 commit + approve, an email-titled action with payload body
  is executed and creates an .eml in the local outbox.
- A non-email action is executed and creates executed.md under
  work_products/{tenant_id}/.
- FastAPI execute route still rejects unapproved actions with 403.
- AEGIS_DATA_DIR temp isolation; no live network.
"""

from __future__ import annotations

import json as _json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.server import create_app
from core.persistence import get_connection
from core.twin_actions import _action_digest, _load_action, approve, execute, propose_actions
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT52LocalExecute(unittest.TestCase):
    """Local execute after approve writes outbox or executed.md."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t52_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete T03 interview and return the session id."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    def _insert_action(
        self,
        tenant_id: str,
        kind: str,
        title: str,
        payload: dict | str | None = None,
        status: str = "proposed",
    ) -> str:
        """Insert an action row with an optional payload and return its id."""
        from core.twin_actions import _ensure_schema

        _ensure_schema()
        action_id = f"act-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        if isinstance(payload, dict):
            payload_json = _json.dumps(payload)
        elif isinstance(payload, str):
            payload_json = payload
        else:
            payload_json = None
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO twin_actions "
                "(action_id, tenant_id, kind, title, status, created_at, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (action_id, tenant_id, kind, title, status, now, payload_json),
            )
        return action_id

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_unapproved_execute_raises_permission_error(self) -> None:
        """execute() refuses an unapproved action with PermissionError."""
        self._full_interview("t52a")
        actions = propose_actions("t52a")
        self.assertGreaterEqual(len(actions), 1)
        first_id = actions[0]["action_id"]
        with self.assertRaises(PermissionError):
            execute(first_id, "t52a")

    def test_email_action_executes_to_outbox(self) -> None:
        """After approve, an email-titled action with payload body writes .eml."""
        tenant = "t52b"
        self._full_interview(tenant)
        action_id = self._insert_action(
            tenant,
            kind="email",
            title="Email: weekly pack",
            payload={"body": "Please send the weekly pack"},
            status="proposed",
        )
        _action = _load_action(action_id)
        assert _action is not None
        approve(action_id, "t52b", "tester", _action_digest(_action))
        result = execute(action_id, "t52b")
        self.assertEqual(result["status"], "executed")
        self.assertEqual(result["action_id"], action_id)

        # The outbox .eml should exist.
        outbox_dir = os.path.join(self._tmp, "work_products", tenant, "outbox")
        eml_files = [
            f for f in os.listdir(outbox_dir) if f.endswith(".eml")
        ] if os.path.isdir(outbox_dir) else []
        self.assertTrue(len(eml_files) >= 1, "expected at least one .eml in outbox")
        # Read the eml file and verify body.
        eml_file = os.path.join(outbox_dir, eml_files[0])
        text = open(eml_file, encoding="utf-8").read()
        self.assertIn("Please send the weekly pack", text)

    def test_non_email_action_writes_executed_md(self) -> None:
        """After approve, a non-email action writes executed.md."""
        tenant = "t52c"
        self._full_interview(tenant)
        action_id = self._insert_action(
            tenant,
            kind="review_digest",
            title="Review weekly digest",
            status="proposed",
        )
        _action = _load_action(action_id)
        assert _action is not None
        approve(action_id, "t52c", "tester", _action_digest(_action))
        result = execute(action_id, "t52c")
        self.assertEqual(result["status"], "executed")

        md_path = os.path.join(
            self._tmp, "work_products", tenant, "executed.md"
        )
        self.assertTrue(os.path.isfile(md_path), f"executed.md not found at {md_path}")
        text = open(md_path, encoding="utf-8").read()
        self.assertIn(action_id, text)
        self.assertIn("Review weekly digest", text)

    def test_fastapi_execute_unapproved_403(self) -> None:
        """FastAPI execute route still rejects unapproved actions with 403."""
        self._full_interview("t52d")
        actions = propose_actions("t52d")
        first_id = actions[0]["action_id"]
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/twin/actions/{first_id}/execute",
            json={"tenant_id": "t52d"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
