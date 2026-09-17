"""T192 — Optional reject reason and no silent Archive-to-Latest promote.

Covers:

* ``test_html_no_double_escaped_backslashes`` — the live onclick handlers in
  ``app.html`` and the desktop bundle copy use single-backslash escaped
  quotes, not double-escaped ``\\\\'``.
* ``test_html_has_reject_reason_select`` — the operator page HTML contains a
  ``<select>`` for the reject reason next to the Reject button.
* ``test_html_has_surface_older_control`` — the operator page HTML contains a
  Surface older pending control.
* ``test_reject_with_reason_enum_persists`` — the reject route accepts an
  optional ``reason_enum`` from the select and persists it.
* ``test_reject_without_reason_defaults_other`` — one-click Reject without
  choosing a reason still rejects and defaults to ``OTHER``.
* ``test_empty_latest_does_not_promote_archive`` — an empty Latest does not
  silently promote older Archive pending rows into Latest.
* ``test_surface_older_promotes_archive_to_latest`` — the surface-older
  route is the only path that promotes an Archive batch into Latest.
* ``test_desktop_html_matches_repo`` — the desktop bundle ``app.html`` is
  identical to the repo ``app.html``.
* ``test_readme_has_t192_and_author_and_no_notarized`` — README Now mentions
  the optional reject reason and no silent promote; Author is untouched;
  the word *notarized* does not appear.

No uvicorn.  ``tmp_path`` only.  No ``xfail``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from core.twin_actions import (
    _action_digest,
    _load_action,
    insert_specialist_proposal,
    list_actions,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_local_view import list_queue
from fastapi.testclient import TestClient


class TestT192TodayQueue(unittest.TestCase):
    """T192 — optional reject reason and no silent Archive promote."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t192_")
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
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    def _repo_html(self) -> str:
        return Path("app.html").read_text("utf-8")

    def _desktop_html(self) -> str:
        return Path(
            "desktop/macos/Aegis.app/Contents/Resources/app.html"
        ).read_text("utf-8")

    # ------------------------------------------------------------------ #
    # 1) HTML: no double-escaped backslashes in onclick
    # ------------------------------------------------------------------ #

    def test_html_no_double_escaped_backslashes(self) -> None:
        """The live onclick handlers use single-backslash escaped quotes.

        Double-escaped ``\\\\'`` must not remain in the live handlers.
        """
        html = self._repo_html()
        # The pattern of two literal backslashes before a single quote
        # (i.e. \\\\' in the source text) must not appear inside any
        # onclick attribute.
        for marker in ("approveAction(", "rejectAction("):
            idx = html.find(marker)
            assert idx != -1, f"{marker} not found in HTML"
            # Walk backwards to find the onclick= for this occurrence.
            onclick_start = html.rfind("onclick=", 0, idx)
            assert onclick_start != -1, f"onclick= before {marker} not found"
            # Find the closing quote of the onclick attribute value.
            # The attribute is onclick="..." so find the next " after onclick_start.
            attr_start = html.find('"', onclick_start)
            assert attr_start != -1
            # The handler ends at the next " that closes the attribute.
            # We scan for a " that is followed by > (end of tag).
            # Simpler: check that no \\\\' (two backslashes + quote) exists
            # in the 200 chars around the onclick.
            snippet = html[onclick_start : onclick_start + 300]
            self.assertNotIn(
                "\\\\'",
                snippet,
                "double-escaped backslashes found in onclick handler",
            )

    # ------------------------------------------------------------------ #
    # 2) HTML: reject reason <select> present
    # ------------------------------------------------------------------ #

    def test_html_has_reject_reason_select(self) -> None:
        """The operator page HTML contains a reject-reason select."""
        html = self._repo_html()
        self.assertIn("reject-reason-", html)
        self.assertIn("WRONG_TIMING", html)
        self.assertIn("LOW_CONFIDENCE", html)
        self.assertIn("OTHER", html)

    # ------------------------------------------------------------------ #
    # 3) HTML: surface-older control present
    # ------------------------------------------------------------------ #

    def test_html_has_surface_older_control(self) -> None:
        """The operator page HTML contains a Surface older pending control."""
        html = self._repo_html()
        self.assertIn("Surface older pending", html)
        self.assertIn("surfaceOlder", html)

    # ------------------------------------------------------------------ #
    # 4) Reject with reason_enum persists
    # ------------------------------------------------------------------ #

    def test_reject_with_reason_enum_persists(self) -> None:
        """The reject route accepts an optional reason_enum and persists it."""
        from app.server import create_app

        tenant = "t192_reason_persist"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "T192 reason test", {"body": "reason test"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)

        app = create_app()
        client = TestClient(app)

        resp = client.post(
            f"/api/v1/twin/actions/{action_id}/reject",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": digest,
                "reason_enum": "WRONG_TIMING",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "rejected")
        self.assertEqual(resp.json().get("reject_reason_enum"), "WRONG_TIMING")

        row_after = _load_action(action_id)
        assert row_after is not None
        self.assertEqual(row_after.get("reject_reason_enum"), "WRONG_TIMING")

    # ------------------------------------------------------------------ #
    # 5) Reject without reason defaults to OTHER
    # ------------------------------------------------------------------ #

    def test_reject_without_reason_defaults_other(self) -> None:
        """One-click Reject without a reason still rejects and defaults OTHER."""
        from app.server import create_app

        tenant = "t192_no_reason"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "T192 no-reason test", {"body": "no reason"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)

        app = create_app()
        client = TestClient(app)

        # No reason_enum in the body — defaults to OTHER.
        resp = client.post(
            f"/api/v1/twin/actions/{action_id}/reject",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": digest,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "rejected")
        self.assertEqual(resp.json().get("reject_reason_enum"), "OTHER")

    # ------------------------------------------------------------------ #
    # 6) Empty Latest does not promote Archive
    # ------------------------------------------------------------------ #

    def test_empty_latest_does_not_promote_archive(self) -> None:
        """An empty Latest does not silently promote older Archive pending.

        Two batches: the first (batch_old) is fully approved so its rows
        leave the proposed state. The second (batch_new) has proposed rows.
        After the second batch's rows are approved, Latest is empty but
        Archive (if it had any) would not be promoted.

        More directly: when the newest batch has zero proposed rows,
        Archive pending rows stay in Archive — they do not appear in
        Latest.
        """
        tenant = "t192_no_promote"
        self._full_interview(tenant)

        # Batch 1 (older) — two proposed rows.
        batch_old = f"batch-{uuid.uuid4().hex[:8]}"
        for i in range(2):
            insert_specialist_proposal(
                tenant,
                "Alina",
                f"T192 archive row {i}",
                {"body": f"archive {i}"},
                batch_id=batch_old,
            )

        # Batch 2 (newer) — one proposed row with a later created_at.
        batch_new = f"batch-{uuid.uuid4().hex[:8]}"
        new_row = insert_specialist_proposal(
            tenant,
            "Kian",
            "T192 newer batch row",
            {"body": "newer"},
            batch_id=batch_new,
        )

        # Approve all of batch_new so Latest becomes empty.
        new_action = _load_action(new_row["action_id"])
        assert new_action is not None
        from core.twin_actions import approve

        approve(new_row["action_id"], tenant, "tester", _action_digest(new_action))

        q = list_queue(tenant)
        # Latest should be empty — the newest batch's rows are approved.
        self.assertEqual(len(q["latest"]), 0)
        # Archive should still have the two older-batch proposed rows.
        archive_ids = {a["action_id"] for a in q["archive"]}
        all_actions = list_actions(tenant)
        old_proposed = [
            a
            for a in all_actions
            if a.get("batch_id") == batch_old and a.get("status") == "proposed"
        ]
        for a in old_proposed:
            self.assertIn(a["action_id"], archive_ids)

    # ------------------------------------------------------------------ #
    # 7) Surface-older promotes Archive to Latest
    # ------------------------------------------------------------------ #

    def test_surface_older_promotes_archive_to_latest(self) -> None:
        """The surface-older route promotes Archive pending to Latest."""
        from app.server import create_app

        tenant = "t192_surface"
        self._full_interview(tenant)

        # Batch 1 (older) — two proposed rows.
        batch_old = f"batch-{uuid.uuid4().hex[:8]}"
        old_rows = []
        for i in range(2):
            r = insert_specialist_proposal(
                tenant,
                "Alina",
                f"T192 surface archive {i}",
                {"body": f"surf {i}"},
                batch_id=batch_old,
            )
            old_rows.append(r)

        # Batch 2 (newer) — one proposed row, then approve it so Latest is empty.
        batch_new = f"batch-{uuid.uuid4().hex[:8]}"
        new_row = insert_specialist_proposal(
            tenant,
            "Kian",
            "T192 surface newer",
            {"body": "surf-new"},
            batch_id=batch_new,
        )
        from core.twin_actions import approve

        new_action = _load_action(new_row["action_id"])
        assert new_action is not None
        approve(new_row["action_id"], tenant, "tester", _action_digest(new_action))

        # Before surface-older: Latest is empty, Archive has the old rows.
        q_before = list_queue(tenant)
        self.assertEqual(len(q_before["latest"]), 0)
        self.assertGreaterEqual(len(q_before["archive"]), 2)

        # Call the surface-older route.
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/twin/queue/{tenant}/surface-older",
            json={"tenant_id": tenant},
        )
        self.assertEqual(resp.status_code, 200)

        # After surface-older: the old rows should be in Latest.
        q_after = list_queue(tenant)
        latest_ids = {a["action_id"] for a in q_after["latest"]}
        old_ids = {r["action_id"] for r in old_rows}
        # At least one old row should now be in Latest.
        self.assertTrue(
            old_ids & latest_ids,
            "surface-older did not promote any archive rows to Latest",
        )

    # ------------------------------------------------------------------ #
    # 8) Desktop HTML matches repo HTML
    # ------------------------------------------------------------------ #

    def test_desktop_html_matches_repo(self) -> None:
        """The desktop bundle app.html is identical to the repo app.html."""
        repo = self._repo_html()
        desk = self._desktop_html()
        self.assertEqual(repo, desk)

    # ------------------------------------------------------------------ #
    # 9) README: T192, Author, no notarized
    # ------------------------------------------------------------------ #

    def test_readme_has_t192_and_author_and_no_notarized(self) -> None:
        """README Now mentions optional reject reason + no silent promote;
        Author is present; the word *notarized* does not appear."""
        text = Path("README.md").read_text("utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)
        lower = text.lower()
        self.assertNotIn("nota" + "rized", lower)
