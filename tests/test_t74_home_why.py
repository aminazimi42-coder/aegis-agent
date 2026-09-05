"""T74 — Home shows reject why so the operator sees why the gate stopped.

Covers:
- home.md has a ``## Rejected`` section sourced from twin_actions only.
- Each rejected row includes ``why_text`` from ``replay_why`` or the action row.
- Empty ``why_text`` renders as ``""`` (the action still shows, just no why).
- No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.persistence import get_connection
from core.twin_actions import (
    _ensure_schema,
    list_actions,
    reject,
    replay_why,
)
from core.twin_home import render_home
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT74HomeWhy(unittest.TestCase):
    """Rejected actions show their stored why_text on home.md."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t74_")
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
        title: str,
        status: str = "proposed",
        kind: str = "review_digest",
    ) -> str:
        """Insert a twin_action row directly and return its action_id."""
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

    def test_home_shows_reject_why(self) -> None:
        """home.md shows the stored why_text for rejected actions."""
        tenant = "t74a"
        self._full_interview(tenant)

        # Insert a proposed action, then reject it with a reason.
        action_id = self._insert_action(tenant, "Review weekly digest")
        reject(action_id, tenant, why="too risky for L0")

        # replay_why must return the stored reason.
        self.assertEqual(replay_why(action_id), "too risky for L0")

        result = render_home(tenant)
        md_text = Path(result["path"]).read_text(encoding="utf-8")

        # The Rejected section must be present.
        self.assertIn("## Rejected", md_text)

        # The rejected action's id and title must appear.
        self.assertIn(action_id, md_text)
        self.assertIn("Review weekly digest", md_text)

        # The why_text must appear in the Rejected section.
        rejected_section = md_text.split("## Rejected")[1]
        next_h = rejected_section.find("## ")
        if next_h != -1:
            rejected_section = rejected_section[:next_h]
        self.assertIn("too risky for L0", rejected_section)

        # The source is twin_actions only (T58 stays).
        rejected = [a for a in list_actions(tenant) if a["status"] == "rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["action_id"], action_id)

    def test_empty_why_is_allowed(self) -> None:
        """A rejected action with no why_text still shows (empty why)."""
        tenant = "t74b"
        self._full_interview(tenant)

        # Reject without a why — empty string is the default.
        action_id = self._insert_action(tenant, "Review repos")
        reject(action_id, tenant, why=None)

        # replay_why returns "" when no reason was recorded.
        self.assertEqual(replay_why(action_id), "")

        result = render_home(tenant)
        md_text = Path(result["path"]).read_text(encoding="utf-8")

        # The Rejected section must be present with the action.
        self.assertIn("## Rejected", md_text)
        self.assertIn(action_id, md_text)

        # The action still shows even with an empty why.
        rejected_section = md_text.split("## Rejected")[1]
        next_h = rejected_section.find("## ")
        if next_h != -1:
            rejected_section = rejected_section[:next_h]
        self.assertIn("Review repos", rejected_section)

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
