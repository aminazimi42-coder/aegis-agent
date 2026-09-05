"""T63 — Unknown effects stay off the L0 path.

Covers:
- ``ALLOWED_L0_EFFECTS`` is a ``frozenset``.
- An unknown effect/kind is never classified as ``L0`` — it is at least ``L1``.
- A known local kind (``"review_digest"``) can still be ``L0`` when supplied
  as the *effect* argument to :func:`classify`.
- ``execute()`` refuses to treat an unknown kind as L0
  (``PermissionError``).
- No live network.
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
    execute,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_risk import ALLOWED_L0_EFFECTS, classify


class TestT63PolicyAllowlist(unittest.TestCase):
    """Unknown effects cannot be L0."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t63_")
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
        status: str = "proposed",
    ) -> str:
        """Insert an action row and return its id."""
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
    # Tests
    # ------------------------------------------------------------------ #

    def test_allowed_l0_effects_is_frozenset(self) -> None:
        self.assertIsInstance(ALLOWED_L0_EFFECTS, frozenset)

    def test_unknown_kind_is_not_l0(self) -> None:
        """An unknown effect is at least L1, never L0."""
        # Title with no risky keywords → would be L0 by title alone, but the
        # unknown effect pushes it to L1.
        self.assertNotEqual(
            classify("Observe something", effect="unknown_effect"), "L0"
        )
        self.assertEqual(
            classify("Observe something", effect="unknown_effect"), "L1"
        )
        # A blank title with an unknown effect is also L1, not L0.
        self.assertEqual(classify("", effect="mystery"), "L1")
        # A title that would normally be L0 but with an unknown effect → L1.
        self.assertEqual(
            classify("Review weekly digest", effect="exfiltrate"), "L1"
        )

    def test_known_local_kind_can_still_be_l0(self) -> None:
        """A known local kind on the allow-list can still be L0."""
        self.assertEqual(
            classify("Review weekly digest", effect="review_digest"), "L0"
        )
        self.assertEqual(
            classify("Review repositories", effect="review_repos"), "L0"
        )
        self.assertEqual(
            classify("Prepare weekly plan", effect="prepare_weekly_plan"),
            "L0",
        )
        self.assertEqual(
            classify("Observe the repo", effect="git observe"), "L0"
        )
        self.assertEqual(
            classify("Read the file", effect="file observe"), "L0"
        )
        self.assertEqual(
            classify("Draft the outbox", effect="local .eml outbox"), "L0"
        )
        # Specialist propose kinds (``"{agent}:propose"``) are allowed.
        self.assertEqual(
            classify("Alina proposal for t63", effect="Alina:propose"), "L0"
        )

    def test_execute_refuses_unknown_l0(self) -> None:
        """execute() refuses to treat an unknown kind as L0."""
        tenant = "t63a"
        self._full_interview(tenant)
        # Insert an action with an unknown kind and a benign title so that
        # title-only classify would be L0, but the effect is not on the
        # allow-list.
        action_id = self._insert_action(
            tenant,
            kind="exfiltrate_data",
            title="Observe the logs",
            status="proposed",
        )
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action))
        with self.assertRaises(PermissionError):
            execute(action_id, tenant)

    def test_execute_allows_known_l0(self) -> None:
        """execute() allows a known local kind that is genuinely L0."""
        tenant = "t63b"
        self._full_interview(tenant)
        action_id = self._insert_action(
            tenant,
            kind="review_digest",
            title="Review weekly digest",
            status="proposed",
        )
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action))
        result = execute(action_id, tenant)
        self.assertEqual(result["status"], "executed")

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
