"""T64 — why-replay survives process restart."""

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
    reject,
    replay_why,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT64WhyReplay(unittest.TestCase):
    """The reason an action was approved/rejected survives a new connection."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t64_")
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
    def test_approve_why_survives_new_connection(self) -> None:
        """approve(..., why=...) stores why_text and replay_why reads it back."""
        self._full_interview("t64a")
        tenant = "t64a"
        action_id = self._insert_action(tenant, title="Review weekly digest")
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)

        reason = "Manual approval for weekly review"
        approve(action_id, tenant, "tester", digest, why=reason)

        # replay_why opens a fresh connection — the reason must persist.
        self.assertEqual(replay_why(action_id), reason)

    def test_reject_why_survives_new_connection(self) -> None:
        """reject(..., why=...) stores why_text and replay_why reads it back."""
        self._full_interview("t64b")
        tenant = "t64b"
        action_id = self._insert_action(tenant, title="Review weekly digest")

        reason = "Rejected: needs human review before approval"
        reject(action_id, tenant, why=reason)

        # replay_why opens a fresh connection — the reason must persist.
        self.assertEqual(replay_why(action_id), reason)


if __name__ == "__main__":
    unittest.main()
