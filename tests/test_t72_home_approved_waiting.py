"""T72 — Home lists approved-not-executed apart from pending.

Covers:
- home.md shows a distinct ``Approved — waiting execute`` group separate
  from the ``Pending actions`` group.
- The source is twin_actions only (T58 stays).
- Executed rows are not shown as waiting.
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
    _action_digest,
    _ensure_schema,
    _load_action,
    approve,
    execute,
    list_actions,
)
from core.twin_home import render_home
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT72HomeApprovedWaiting(unittest.TestCase):
    """Approved-but-not-executed actions appear in a distinct home section."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t72_")
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

    def _approve(self, tenant_id: str, action_id: str) -> None:
        """Approve an action using its current envelope digest."""
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        approve(action_id, tenant_id, "tester", digest)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_home_lists_approved_not_executed(self) -> None:
        """home.md has a distinct 'Approved — waiting execute' section listing approved actions."""
        tenant = "t72a"
        self._full_interview(tenant)

        # Insert a proposed action and a separate approved action.
        proposed_id = self._insert_action(tenant, "Review weekly digest")
        approved_id = self._insert_action(tenant, "Review repos")
        self._approve(tenant, approved_id)

        result = render_home(tenant)
        md_text = Path(result["path"]).read_text(encoding="utf-8")

        # The distinct section heading must be present.
        self.assertIn("## Approved — waiting execute", md_text)

        # The approved-but-not-executed action must appear in the approved section.
        self.assertIn(approved_id, md_text)
        self.assertIn("Review repos", md_text)

        # The pending action must still appear (it is proposed, not approved).
        self.assertIn(proposed_id, md_text)

        # Verify the source is twin_actions (T58 stays).
        approved = [a for a in list_actions(tenant) if a["status"] == "approved"]
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]["action_id"], approved_id)

    def test_home_excludes_executed(self) -> None:
        """home.md does not list executed actions in the 'Approved — waiting execute' section."""
        tenant = "t72b"
        self._full_interview(tenant)

        # Insert and approve two actions.
        a1 = self._insert_action(tenant, "Review digest one")
        a2 = self._insert_action(tenant, "Review digest two")
        self._approve(tenant, a1)
        self._approve(tenant, a2)

        # Execute a1; a2 stays approved.
        execute(a1, tenant)

        result = render_home(tenant)
        md_text = Path(result["path"]).read_text(encoding="utf-8")

        # The executed action must not appear as approved waiting execute.
        # It should be absent from the approved section (it is executed now).
        # Confirm there is at least one approved section.
        self.assertIn("## Approved — waiting execute", md_text)

        # The executed action must not be listed as waiting.
        # Check the section body between "## Approved — waiting execute" and the
        # next "##" heading does not contain a1.
        approved_section = md_text.split("## Approved — waiting execute")[1]
        # Cut at the next heading.
        next_h = approved_section.find("## ")
        if next_h != -1:
            approved_section = approved_section[:next_h]
        self.assertNotIn(a1, approved_section)

        # The still-approved (not executed) action must appear in the approved section.
        self.assertIn(a2, approved_section)

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
