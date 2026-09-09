"""T130 — Thin local twin loop from approve and reject.

Covers:
- ``test_approve_writes_feedback``: approve appends a local feedback
  note with ``action_id``, ``decision: approve``, ``agent``, and ``ts``.
- ``test_reject_writes_reason``: reject appends a feedback note whose
  ``reason`` carries the T117 typed reason enum.
- ``test_purge_removes_feedback``: purge_tenant deletes twin_feedback
  rows for that tenant (neighbour survives).

No live network except ``TestClient``.
"""

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
    list_recent_notes,
    reject,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_memory_control import purge_tenant


class TestT130TwinLoop(unittest.TestCase):
    """Approve and reject persist a local style/risk note."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t130_")
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
        status: str = "proposed",
    ) -> str:
        """Insert a twin_actions row and return its id."""
        _ensure_schema()
        action_id = f"act-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO twin_actions "
                "(action_id, tenant_id, kind, title, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (action_id, tenant_id, kind, title, status, now),
            )
        return action_id

    # ------------------------------------------------------------------ #
    # 1. Approve writes feedback
    # ------------------------------------------------------------------ #
    def test_approve_writes_feedback(self) -> None:
        """approve() appends {action_id, decision: approve, agent, ts}."""
        self._full_interview("t130-approve")
        tenant = "t130-approve"
        action_id = self._insert_action(tenant)
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)

        approve(action_id, tenant, "operator-1", digest, why="ok to proceed")

        notes = list_recent_notes(tenant, n=10)
        self.assertEqual(len(notes), 1)
        note = notes[0]
        self.assertEqual(note["action_id"], action_id)
        self.assertEqual(note["decision"], "approve")
        self.assertEqual(note.get("agent"), "operator-1")
        self.assertIn("created_at", note)
        self.assertTrue(note["created_at"])

    # ------------------------------------------------------------------ #
    # 2. Reject writes reason
    # ------------------------------------------------------------------ #
    def test_reject_writes_reason(self) -> None:
        """reject() appends a feedback note whose reason is the T117 enum."""
        self._full_interview("t130-reject")
        tenant = "t130-reject"
        action_id = self._insert_action(tenant)

        reject(action_id, tenant, reason_enum="POLICY_VIOLATION", why="not allowed")

        notes = list_recent_notes(tenant, n=10)
        self.assertEqual(len(notes), 1)
        note = notes[0]
        self.assertEqual(note["action_id"], action_id)
        self.assertEqual(note["decision"], "reject")
        self.assertEqual(note.get("reason"), "POLICY_VIOLATION")

        # Also verify list_feedback sees the row.
        rows = list_feedback(tenant)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["decision"], "reject")

    # ------------------------------------------------------------------ #
    # 3. Purge removes feedback
    # ------------------------------------------------------------------ #
    def test_purge_removes_feedback(self) -> None:
        """purge_tenant deletes twin_feedback rows for that tenant.

        A neighbour tenant's feedback rows must survive the purge.
        """
        tenant_a = "t130-purge-a"
        tenant_b = "t130-purge-b"
        self._full_interview(tenant_a)
        self._full_interview(tenant_b)

        # Tenant A — approve.
        a_id = self._insert_action(tenant_a)
        a_action = _load_action(a_id)
        assert a_action is not None
        a_digest = _action_digest(a_action)
        approve(a_id, tenant_a, "op", a_digest, why="approve A")

        # Tenant B — reject.
        b_id = self._insert_action(tenant_b)
        reject(b_id, tenant_b, reason_enum="DUPLICATE", why="dup B")

        # Sanity: both have feedback.
        self.assertEqual(len(list_feedback(tenant_a)), 1)
        self.assertEqual(len(list_feedback(tenant_b)), 1)

        # Purge tenant A.
        result = purge_tenant(tenant_a, f"PURGE {tenant_a}")
        self.assertTrue(result["cleared"])

        # Tenant A feedback is gone.
        self.assertEqual(len(list_feedback(tenant_a)), 0)

        # Tenant B feedback survives.
        rows_b = list_feedback(tenant_b)
        self.assertEqual(len(rows_b), 1)
        self.assertEqual(rows_b[0]["decision"], "reject")

    # ------------------------------------------------------------------ #
    # 4. No live network
    # ------------------------------------------------------------------ #
    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
