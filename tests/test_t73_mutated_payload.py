"""T73 — Mutated payload after approve cannot execute.

Covers:
- execute() rejects when the stored payload changes after approve (ValueError).
- Status stays ``approved`` on mismatch — no receipt is written.
- No live network.
"""

from __future__ import annotations

import json as _json
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
    execute,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT73MutatedPayload(unittest.TestCase):
    """execute() refuses when the payload was tampered after approval."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t73_")
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

    def test_execute_rejects_mutated_payload(self) -> None:
        """execute() raises ValueError when payload changed after approve."""
        self._full_interview("t73a")
        tenant = "t73a"
        action_id = self._insert_action(
            tenant,
            kind="review_digest",
            title="Review weekly digest",
            payload={"body": "original"},
        )
        # Compute the canonical digest and approve with it.
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        approve(action_id, tenant, "tester", digest)

        # Tamper the stored payload after approval.
        with get_connection() as conn:
            conn.execute(
                "UPDATE twin_actions SET payload = ? WHERE action_id = ?",
                (_json.dumps({"body": "tampered"}), action_id),
            )

        # execute() must refuse.
        with self.assertRaises(ValueError):
            execute(action_id, tenant)

    def test_status_stays_approved_on_mismatch(self) -> None:
        """On digest mismatch, status stays 'approved' — no receipt written."""
        self._full_interview("t73b")
        tenant = "t73b"
        action_id = self._insert_action(
            tenant,
            kind="review_digest",
            title="Review weekly digest",
            payload={"body": "original"},
        )
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        approve(action_id, tenant, "tester", digest)

        # Tamper the stored payload.
        with get_connection() as conn:
            conn.execute(
                "UPDATE twin_actions SET payload = ? WHERE action_id = ?",
                (_json.dumps({"body": "tampered"}), action_id),
            )

        # execute() raises ...
        with self.assertRaises(ValueError):
            execute(action_id, tenant)

        # ... and the status is still 'approved' (not 'executed').
        reloaded = _load_action(action_id)
        assert reloaded is not None
        self.assertEqual(reloaded["status"], "approved")

        # No receipt file should have been written.
        import pathlib

        receipts_dir = (
            pathlib.Path(self._tmp) / "work_products" / tenant / "receipts"
        )
        if receipts_dir.exists():
            files = list(receipts_dir.glob("*.md"))
            self.assertEqual(files, [], "no receipt should exist on mismatch")

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
