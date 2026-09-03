"""T49 — Email outbox uses action payload body.

Covers:
- send_approved writes an .eml whose text contains the payload body
  ("Please send the pack") when payload is a dict with a ``body`` key.
- FastAPI send route still 400 without profile or unapproved action.
- No socket / no network.
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
from core.twin_email_send import send_approved
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT49EmailPayloadBody(unittest.TestCase):
    """Outbox .eml body comes from the action payload."""

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

    def _insert_email_action(
        self,
        tenant_id: str,
        title: str,
        payload: dict | str | None = None,
        status: str = "proposed",
    ) -> str:
        """Insert an email-like action with an optional payload."""
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
                (action_id, tenant_id, "email", title, status, now, payload_json),
            )
        return action_id

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_payload_dict_body_in_eml(self) -> None:
        """The .eml body contains payload['body'] when payload is a dict."""
        self._full_interview("t49a")
        action_id = self._insert_email_action(
            "t49a",
            "Draft: pack request",
            payload={"body": "Please send the pack"},
            status="approved",
        )
        result = send_approved("t49a", action_id)
        self.assertEqual(result["action_id"], action_id)

        eml_path = os.path.join(
            self._tmp, "work_products", "t49a", "outbox", f"{action_id}.eml"
        )
        self.assertTrue(os.path.isfile(eml_path))
        text = open(eml_path, encoding="utf-8").read()
        self.assertIn("Please send the pack", text)

    def test_payload_dict_text_key_in_eml(self) -> None:
        """The .eml body falls back to payload['text'] when 'body' is absent."""
        self._full_interview("t49b")
        action_id = self._insert_email_action(
            "t49b",
            "Draft: follow-up",
            payload={"text": "Follow-up text"},
            status="approved",
        )
        send_approved("t49b", action_id)
        eml_path = os.path.join(
            self._tmp, "work_products", "t49b", "outbox", f"{action_id}.eml"
        )
        text = open(eml_path, encoding="utf-8").read()
        self.assertIn("Follow-up text", text)

    def test_payload_dict_draft_key_in_eml(self) -> None:
        """The .eml body falls back to payload['draft'] when 'body'/'text' absent."""
        self._full_interview("t49c")
        action_id = self._insert_email_action(
            "t49c",
            "Draft: memo",
            payload={"draft": "Draft body text"},
            status="approved",
        )
        send_approved("t49c", action_id)
        eml_path = os.path.join(
            self._tmp, "work_products", "t49c", "outbox", f"{action_id}.eml"
        )
        text = open(eml_path, encoding="utf-8").read()
        self.assertIn("Draft body text", text)

    def test_payload_str_body_in_eml(self) -> None:
        """The .eml body uses the raw string payload when payload is a str."""
        self._full_interview("t49d")
        action_id = self._insert_email_action(
            "t49d",
            "Draft: string payload",
            payload="Raw string body",
            status="approved",
        )
        send_approved("t49d", action_id)
        eml_path = os.path.join(
            self._tmp, "work_products", "t49d", "outbox", f"{action_id}.eml"
        )
        text = open(eml_path, encoding="utf-8").read()
        self.assertIn("Raw string body", text)

    def test_payload_none_falls_back_to_title(self) -> None:
        """When no payload is present, the body falls back to the title."""
        self._full_interview("t49e")
        action_id = self._insert_email_action(
            "t49e",
            "Draft: no payload",
            payload=None,
            status="approved",
        )
        send_approved("t49e", action_id)
        eml_path = os.path.join(
            self._tmp, "work_products", "t49e", "outbox", f"{action_id}.eml"
        )
        text = open(eml_path, encoding="utf-8").read()
        self.assertIn("Subject: Draft: no payload", text)
        # body should contain the title too
        self.assertIn("Draft: no payload", text)

    def test_fastapi_email_send_400_without_profile(self) -> None:
        """FastAPI send route still 400 without a consented profile."""
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/email/send",
            json={"tenant_id": "no_profile_t49_api", "action_id": "act-none"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_fastapi_email_send_400_unapproved(self) -> None:
        """FastAPI send route still 400 for an unapproved action."""
        self._full_interview("t49f")
        action_id = self._insert_email_action(
            "t49f",
            "Draft: still proposed",
            payload={"body": "Please send the pack"},
            status="proposed",
        )
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/email/send",
            json={"tenant_id": "t49f", "action_id": action_id},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
