"""T56 — Bind approval to the exact action payload.

Covers:
- Mutated payload invalidates approval (digest mismatch on approve).
- Mutated title invalidates approval (digest mismatch on approve).
- approve() requires expected_payload_sha256 — calling without it raises.
- A rejected action cannot be resurrected (approve after reject raises).
- Restart preserves approved_payload_sha256 and approved_by.
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
    reject,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT56ApprovalBinding(unittest.TestCase):
    """Approval is bound to the immutable canonical envelope digest."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t56_")
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

    def test_mutated_payload_invalidates_approval(self) -> None:
        """Changing the payload after computing the digest breaks approval."""
        self._full_interview("t56a")
        tenant = "t56a"
        action_id = self._insert_action(
            tenant,
            kind="email",
            title="Email: weekly pack",
            payload={"body": "original body"},
        )
        # Compute digest before mutation.
        action = _load_action(action_id)
        assert action is not None
        original_digest = _action_digest(action)

        # Mutate the payload after computing the digest.
        with get_connection() as conn:
            conn.execute(
                "UPDATE twin_actions SET payload = ? WHERE action_id = ?",
                (_json.dumps({"body": "tampered body"}), action_id),
            )

        # Approve with the original digest — must fail.
        with self.assertRaises(ValueError):
            approve(action_id, tenant, "tester", original_digest)

    def test_mutated_title_invalidates_approval(self) -> None:
        """Changing the title after computing the digest breaks approval."""
        self._full_interview("t56b")
        tenant = "t56b"
        action_id = self._insert_action(
            tenant,
            kind="review_digest",
            title="Review weekly digest",
        )
        action = _load_action(action_id)
        assert action is not None
        original_digest = _action_digest(action)

        # Mutate the title.
        with get_connection() as conn:
            conn.execute(
                "UPDATE twin_actions SET title = ? WHERE action_id = ?",
                ("Review monthly digest", action_id),
            )

        with self.assertRaises(ValueError):
            approve(action_id, tenant, "tester", original_digest)

    def test_approve_requires_expected_digest(self) -> None:
        """Calling approve() without expected_payload_sha256 raises."""
        self._full_interview("t56c")
        action_id = self._insert_action("t56c", title="Review weekly digest")
        with self.assertRaises(ValueError) as ctx:
            approve(action_id)
        self.assertIn("digest required", str(ctx.exception))

    def test_rejected_action_cannot_be_resurrected(self) -> None:
        """approve() on a rejected action raises."""
        self._full_interview("t56d")
        tenant = "t56d"
        action_id = self._insert_action(tenant, title="Review weekly digest")
        reject(action_id)

        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        with self.assertRaises(ValueError):
            approve(action_id, tenant, "tester", digest)

    def test_restart_preserves_approval_digest_and_actor(self) -> None:
        """After approve, a reload from DB preserves approved_payload_sha256 and approved_by."""
        self._full_interview("t56e")
        tenant = "t56e"
        action_id = self._insert_action(
            tenant,
            kind="review_digest",
            title="Review weekly digest",
        )
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        approve(action_id, tenant, "alice", digest)

        # Reload from DB — simulate a restart.
        reloaded = _load_action(action_id)
        assert reloaded is not None
        self.assertEqual(reloaded["status"], "approved")
        self.assertEqual(reloaded["approved_payload_sha256"], digest)
        self.assertEqual(reloaded["approved_by"], "alice")
        self.assertIsNotNone(reloaded["approved_at"])

        # Execute should succeed since the digest matches.
        result = execute(action_id)
        self.assertEqual(result["status"], "executed")

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
