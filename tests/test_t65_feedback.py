"""T65 — Persist approve and reject feedback rows."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from core.persistence import get_connection
from core.twin_actions import (
    _action_digest,
    _ensure_schema,
    _load_action,
    approve,
    list_feedback,
    reject,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT65Feedback(unittest.TestCase):
    """Each approve or reject appends one durable feedback row."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t65_")
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
        kind: str = "review_digest",
        title: str = "Review weekly digest",
        payload: dict | str | None = None,
        status: str = "proposed",
    ) -> str:
        """Insert an action row with optional payload and return its id."""
        import json as _json

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
    def test_approve_writes_feedback_row(self) -> None:
        """approve() inserts one row into twin_feedback with decision='approve'."""
        self._full_interview("t65a")
        tenant = "t65a"
        action_id = self._insert_action(tenant, title="Review weekly digest")
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)

        reason = "Approved for weekly review"
        approve(action_id, tenant, "tester", digest, why=reason)

        rows = list_feedback(tenant)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action_id"], action_id)
        self.assertEqual(rows[0]["tenant_id"], tenant)
        self.assertEqual(rows[0]["decision"], "approve")
        self.assertEqual(rows[0]["why_text"], reason)

    def test_reject_writes_feedback_row(self) -> None:
        """reject() inserts one row into twin_feedback with decision='reject'."""
        self._full_interview("t65b")
        tenant = "t65b"
        action_id = self._insert_action(tenant, title="Review weekly digest")

        reason = "Rejected: needs more review"
        reject(action_id, tenant, why=reason)

        rows = list_feedback(tenant)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action_id"], action_id)
        self.assertEqual(rows[0]["tenant_id"], tenant)
        self.assertEqual(rows[0]["decision"], "reject")
        self.assertEqual(rows[0]["why_text"], reason)

    def test_list_feedback_is_tenant_scoped(self) -> None:
        """list_feedback returns only the requested tenant's rows."""
        self._full_interview("t65c1")
        self._full_interview("t65c2")

        # Tenant 1 — approve
        a1 = self._insert_action("t65c1", title="Review weekly digest")
        action1 = _load_action(a1)
        assert action1 is not None
        d1 = _action_digest(action1)
        approve(a1, "t65c1", "tester", d1, why="ok")

        # Tenant 2 — reject
        a2 = self._insert_action("t65c2", title="Review weekly digest")
        reject(a2, "t65c2", why="nope")

        rows1 = list_feedback("t65c1")
        rows2 = list_feedback("t65c2")
        self.assertEqual(len(rows1), 1)
        self.assertEqual(rows1[0]["tenant_id"], "t65c1")
        self.assertEqual(rows1[0]["decision"], "approve")
        self.assertEqual(len(rows2), 1)
        self.assertEqual(rows2[0]["tenant_id"], "t65c2")
        self.assertEqual(rows2[0]["decision"], "reject")


if __name__ == "__main__":
    unittest.main()
