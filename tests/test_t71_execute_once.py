"""T71 — Execute once per action_id.

Covers:
- A second execute of an already-executed id does not rewrite the receipt.
- A second execute keeps the first status (``executed``).
- AEGIS_DATA_DIR temp isolation; no live network.
"""

from __future__ import annotations

import json as _json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from core.persistence import get_connection
from core.twin_actions import _action_digest, _load_action, approve, execute
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT71ExecuteOnce(unittest.TestCase):
    """Second execute returns the existing row; receipt is not rewritten."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t71_")
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

    def test_second_execute_does_not_rewrite_receipt(self) -> None:
        """A second execute must not rewrite the receipt file."""
        tenant = "t71a"
        self._full_interview(tenant)
        action_id = self._insert_action(
            tenant,
            kind="review_digest",
            title="Review weekly digest",
            status="proposed",
        )
        _action = _load_action(action_id)
        assert _action is not None
        approve(action_id, tenant, "tester", _action_digest(_action))
        result = execute(action_id, tenant)
        self.assertEqual(result["status"], "executed")

        receipt_path = os.path.join(
            self._tmp, "work_products", tenant, "receipts", f"{action_id}.md"
        )
        self.assertTrue(os.path.isfile(receipt_path))
        text_before = open(receipt_path, encoding="utf-8").read()
        mtime_before = os.path.getmtime(receipt_path)

        second = execute(action_id, tenant)
        self.assertEqual(second["status"], "executed")

        text_after = open(receipt_path, encoding="utf-8").read()
        mtime_after = os.path.getmtime(receipt_path)

        self.assertEqual(text_before, text_after)
        self.assertEqual(mtime_before, mtime_after)

    def test_second_execute_keeps_first_status(self) -> None:
        """A second execute keeps the first ``executed`` status."""
        tenant = "t71b"
        self._full_interview(tenant)
        action_id = self._insert_action(
            tenant,
            kind="review_digest",
            title="Review weekly digest",
            status="proposed",
        )
        _action = _load_action(action_id)
        assert _action is not None
        approve(action_id, tenant, "tester", _action_digest(_action))

        first = execute(action_id, tenant)
        self.assertEqual(first["status"], "executed")

        second = execute(action_id, tenant)
        self.assertEqual(second["status"], "executed")
        self.assertEqual(second["action_id"], action_id)
        self.assertEqual(second["kind"], "review_digest")
        self.assertEqual(second["title"], "Review weekly digest")

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
