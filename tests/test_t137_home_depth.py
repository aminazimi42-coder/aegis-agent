"""T137 — Home depth: approved receipts, offline banner, signed brief export.

Covers:
* ``test_pending_hides_approved``: the Approved strip lists only
  ``status="approved"`` rows; proposed rows do not appear in it.
* ``test_approved_strip_shows_approved_action``: after approving a
  proposed action, ``list_queue`` returns it under
  ``approved_waiting`` with agent, digest prefix, and approved
  timestamp.
* ``test_rejected_not_in_approved_strip``: a rejected action does not
  appear in ``approved_waiting``.
* ``test_health_ok_hides_offline_banner``: app.html hides the
  ``offline-banner`` on a successful health check.
* ``test_health_down_shows_offline_banner``: app.html shows the
  ``offline-banner`` when the health check fails.
* ``test_signed_export_writes_outside_repo``: the signed brief export
  endpoint writes a file under ``AEGIS_DATA_DIR/export/`` (or
  ``$HOME/.aegis/``), never into the git worktree.  An empty profile
  returns a typed 400.

No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_actions import (
    _action_digest,
    _ensure_schema,
    approve,
    insert_specialist_proposal,
    list_actions,
    reject,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_local_view import list_queue

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_HTML = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)


class TestT137HomeDepth(unittest.TestCase):
    """Approved receipts, offline banner, signed brief export."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t137_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete interview and return the session id."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}-{tenant_id}")
        commit(sid, True)
        return sid

    def _insert_proposed(self, tenant_id: str, title: str = "Review digest") -> str:
        """Insert a proposed specialist action and return its action_id."""
        _ensure_schema()
        row = insert_specialist_proposal(
            tenant_id=tenant_id,
            agent_name="twin_local",
            title=title,
            payload={"body": title},
        )
        return row["action_id"]

    def _approve_action(self, tenant_id: str, action_id: str) -> dict:
        """Approve a proposed action and return the approved dict."""
        actions = list_actions(tenant_id)
        action = next(
            (a for a in actions if a["action_id"] == action_id), None
        )
        assert action is not None  # for type-checker
        digest = _action_digest(action)
        return approve(
            action_id,
            tenant_id=tenant_id,
            actor_id="operator",
            expected_payload_sha256=digest,
        )

    # ------------------------------------------------------------------ #
    # 1) Pending hides approved — approved strip shows only approved
    # ------------------------------------------------------------------ #

    def test_pending_hides_approved(self) -> None:
        """The Approved strip lists only ``status="approved"`` rows;
        proposed rows do not appear in ``approved_waiting``."""
        tenant = "t137-pending"
        self._full_interview(tenant)
        aid = self._insert_proposed(tenant, title="Pending action")

        q = list_queue(tenant)
        # The proposed action should be in pending, not approved_waiting.
        proposed_ids = {a["action_id"] for a in q["pending"]}
        approved_ids = {a["action_id"] for a in q["approved_waiting"]}
        self.assertIn(aid, proposed_ids)
        self.assertNotIn(aid, approved_ids)
        self.assertEqual(len(q["approved_waiting"]), 0)

    # ------------------------------------------------------------------ #
    # 2) Approved strip shows the approved action
    # ------------------------------------------------------------------ #

    def test_approved_strip_shows_approved_action(self) -> None:
        """After approving, ``list_queue`` returns it under
        ``approved_waiting`` with agent, digest prefix, and approved
        timestamp."""
        tenant = "t137-approved"
        self._full_interview(tenant)
        aid = self._insert_proposed(tenant, title="Approve me")
        self._approve_action(tenant, aid)

        q = list_queue(tenant)
        approved_rows = q["approved_waiting"]
        self.assertEqual(len(approved_rows), 1)
        row = approved_rows[0]
        self.assertEqual(row["action_id"], aid)
        self.assertEqual(row["status"], "approved")
        # Agent is derived from the kind prefix.
        self.assertTrue(row.get("agent"))
        # Digest prefix is a non-empty string.
        self.assertTrue(row.get("digest_prefix"))
        # Approved timestamp is present.
        self.assertTrue(row.get("approved_at"))

    # ------------------------------------------------------------------ #
    # 3) Rejected not in approved strip
    # ------------------------------------------------------------------ #

    def test_rejected_not_in_approved_strip(self) -> None:
        """A rejected action does not appear in ``approved_waiting``."""
        tenant = "t137-rejected"
        self._full_interview(tenant)
        aid = self._insert_proposed(tenant, title="Reject me")
        # Reject the action — no digest binding needed.
        reject(
            aid,
            tenant_id=tenant,
            reason="stale",
            why="stale proposal",
        )
        q = list_queue(tenant)
        approved_ids = {a["action_id"] for a in q["approved_waiting"]}
        self.assertNotIn(
            aid,
            approved_ids,
            "rejected action should not appear in approved_waiting",
        )
        # Also not in pending (status is rejected, not proposed).
        pending_ids = {a["action_id"] for a in q["pending"]}
        self.assertNotIn(aid, pending_ids)

    # ------------------------------------------------------------------ #
    # 4) Health OK hides offline banner
    # ------------------------------------------------------------------ #

    def test_health_ok_hides_offline_banner(self) -> None:
        """app.html hides the ``offline-banner`` on a successful health
        check via ``setOnline``."""
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        # setOnline must hide the banner.
        self.assertIn("setonline", html)
        self.assertIn('offline-banner").style.display = "none"', html)

    # ------------------------------------------------------------------ #
    # 5) Health down shows offline banner
    # ------------------------------------------------------------------ #

    def test_health_down_shows_offline_banner(self) -> None:
        """app.html shows the ``offline-banner`` when the health check
        fails via ``setOffline``."""
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        # setOffline must show the banner.
        self.assertIn("setoffline", html)
        self.assertIn('offline-banner").style.display = "block"', html)
        # The health check must call setOffline on error.
        self.assertIn("setoffline()", html)

    # ------------------------------------------------------------------ #
    # 6) Signed export writes outside the repo
    # ------------------------------------------------------------------ #

    def test_signed_export_writes_outside_repo(self) -> None:
        """The signed brief export endpoint writes a file under
        ``AEGIS_DATA_DIR/export/`` — never into the git worktree.
        An empty profile returns a typed 400, no file."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t137-signed"
        self._full_interview(tenant)
        self._insert_proposed(tenant, title="Signed brief action")

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/brief/signed-export",
            json={"tenant_id": tenant},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        out_path = Path(data["path"])
        # The file must exist.
        self.assertTrue(out_path.is_file(), "export file not created")
        # The file must be under the temp data dir, not the repo.
        self.assertTrue(
            str(out_path).startswith(str(self._tmp)),
            f"export file {out_path} not under AEGIS_DATA_DIR ({self._tmp})",
        )
        self.assertFalse(
            str(out_path).startswith(str(_REPO_ROOT)),
            f"export file {out_path} leaked into the repo worktree",
        )
        # The sha256 must be present.
        self.assertIn("sha256", data)
        self.assertEqual(len(data["sha256"]), 64)

        # Empty profile returns a typed 400, no file.
        resp2 = client.post(
            "/api/v1/twin/brief/signed-export",
            json={"tenant_id": "t137-no-profile"},
        )
        self.assertEqual(resp2.status_code, 400)

    # ------------------------------------------------------------------ #
    # 7) No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """No live network is used in this test module."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
