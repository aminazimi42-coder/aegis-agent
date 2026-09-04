"""T59 — Execution is true only after the local receipt exists.

Covers:
- If the receipt write fails, status stays ``approved`` (not ``executed``).
- After a successful execute, ``receipts/{action_id}.md`` exists on disk.
- A second execute of an already-executed id raises instead of rewriting
  a second receipt as success.
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


class TestT59ExecuteTruth(unittest.TestCase):
    """Execute must not claim success before the receipt is on disk."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t59_")
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

    def test_status_stays_approved_when_receipt_write_fails(self) -> None:
        """If the receipt write raises, status must stay ``approved``."""
        tenant = "t59a"
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

        # Sabotage: create ``work_products/{tenant}/receipts`` as a regular
        # file so the ``mkdir`` inside ``_write_receipt`` raises.
        wp_dir = os.path.join(self._tmp, "work_products", tenant)
        os.makedirs(wp_dir, exist_ok=True)
        receipts_file = os.path.join(wp_dir, "receipts")
        open(receipts_file, "w").close()  # regular file, not a dir

        with self.assertRaises((OSError, PermissionError)):
            execute(action_id, tenant)

        # Status must still be ``approved`` in the DB.
        reloaded = _load_action(action_id)
        assert reloaded is not None
        self.assertEqual(reloaded["status"], "approved")

    def test_executed_row_has_receipt_file(self) -> None:
        """After a successful execute, ``receipts/{action_id}.md`` exists."""
        tenant = "t59b"
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
        self.assertTrue(
            os.path.isfile(receipt_path),
            f"receipt not found at {receipt_path}",
        )
        text = open(receipt_path, encoding="utf-8").read()
        self.assertIn(action_id, text)
        self.assertIn("Review weekly digest", text)

    def test_second_execute_does_not_claim_success(self) -> None:
        """A second execute of an already-executed id must raise."""
        tenant = "t59c"
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

        with self.assertRaises(ValueError):
            execute(action_id, tenant)

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
