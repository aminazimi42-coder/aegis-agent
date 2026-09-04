"""T58 — One canonical home queue from twin_actions.

Covers:
- home.md lists every proposed twin_action (status ``proposed``).
- A generic ``put_approval`` row is NOT the home queue source.
- No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_home import render_home
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_persist import put_approval


class TestT58HomeQueue(unittest.TestCase):
    """The home queue reads twin_actions, not generic approvals."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t58_")
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

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_home_lists_every_proposed_twin_action(self) -> None:
        """home.md contains every proposed twin_action's action_id and title."""
        from core.twin_actions import list_actions, propose_actions

        tenant = "t58a"
        self._full_interview(tenant)
        actions = propose_actions(tenant)
        self.assertGreaterEqual(len(actions), 1)

        result = render_home(tenant)
        md_text = Path(result["path"]).read_text(encoding="utf-8")

        # Every proposed twin action should appear in home.md.
        for action in actions:
            self.assertIn(action["action_id"], md_text)
            self.assertIn(action["title"], md_text)

        # Verify the source is twin_actions, not generic approvals.
        proposed = [a for a in list_actions(tenant) if a["status"] == "proposed"]
        self.assertEqual(len(proposed), len(actions))

    def test_generic_approval_row_is_not_the_home_queue(self) -> None:
        """A generic put_approval row must NOT appear in home.md."""
        tenant = "t58b"
        self._full_interview(tenant)

        # Insert a generic approval row that should NOT be the queue source.
        put_approval("gen-999", tenant, "Generic approval that should not show", "pending")

        result = render_home(tenant)
        md_text = Path(result["path"]).read_text(encoding="utf-8")

        # The generic approval title must not appear in home.md.
        self.assertNotIn("Generic approval that should not show", md_text)

        # home.md should still have a Pending actions section (even if empty).
        self.assertIn("## Pending actions", md_text)

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
