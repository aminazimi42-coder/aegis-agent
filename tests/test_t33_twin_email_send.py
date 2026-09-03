"""T33 — Send an approved email draft to a local outbox.

Covers:
- send_approved without a consented profile raises ValueError.
- After a T03 commit + propose + approve of an email-like action:
  the outbox .eml file exists and contains "local-outbox-only".
- An unapproved action raises ValueError.
- FastAPI 200 on POST /api/v1/twin/email/send.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.server import create_app
from core.persistence import get_connection
from core.twin_email_send import send_approved
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT33TwinEmailSend(unittest.TestCase):
    """Local-outbox email-send invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
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

    def _insert_email_action(self, tenant_id: str, title: str, status: str = "proposed") -> str:
        """Insert an email-like action into twin_actions and return its id."""
        from core.twin_actions import _ensure_schema

        _ensure_schema()
        action_id = f"act-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO twin_actions "
                "(action_id, tenant_id, kind, title, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (action_id, tenant_id, "email", title, status, now),
            )
        return action_id

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_send_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            send_approved("no_profile_t33", "act-nonexistent")

    def test_send_action_not_found_raises_value_error(self) -> None:
        self._full_interview("t33b")
        with self.assertRaises(ValueError):
            send_approved("t33b", "act-nonexistent")

    def test_send_unapproved_raises_value_error(self) -> None:
        self._full_interview("t33c")
        action_id = self._insert_email_action("t33c", "Draft: Q3 update")
        # action is "proposed", not "approved"
        with self.assertRaises(ValueError):
            send_approved("t33c", action_id)

    def test_send_approved_writes_outbox_eml(self) -> None:
        self._full_interview("t33d")
        action_id = self._insert_email_action("t33d", "Draft: Q3 update")

        # Approve the action.
        from core.twin_actions import approve

        approve(action_id)

        result = send_approved("t33d", action_id)

        self.assertEqual(result["tenant_id"], "t33d")
        self.assertEqual(result["action_id"], action_id)

        eml_path = os.path.join(self._tmp, "work_products", "t33d", "outbox", f"{action_id}.eml")
        self.assertEqual(os.path.abspath(result["path"]), os.path.abspath(eml_path))
        self.assertTrue(os.path.isfile(eml_path))

        text = open(eml_path, encoding="utf-8").read()
        self.assertIn("local-outbox-only", text)
        self.assertIn("Subject: Draft: Q3 update", text)

    def test_fastapi_email_send_200(self) -> None:
        self._full_interview("t33e")
        action_id = self._insert_email_action("t33e", "Draft: board memo")

        from core.twin_actions import approve

        approve(action_id)

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/email/send",
            json={"tenant_id": "t33e", "action_id": action_id},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t33e")
        self.assertEqual(body["action_id"], action_id)
        self.assertTrue(os.path.isfile(body["path"]))
        text = open(body["path"], encoding="utf-8").read()
        self.assertIn("local-outbox-only", text)

    def test_fastapi_email_send_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/email/send",
            json={"tenant_id": "no_profile_t33_api", "action_id": "act-none"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_fastapi_email_send_400_unapproved(self) -> None:
        self._full_interview("t33f")
        action_id = self._insert_email_action("t33f", "Draft: still proposed")

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/email/send",
            json={"tenant_id": "t33f", "action_id": action_id},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
