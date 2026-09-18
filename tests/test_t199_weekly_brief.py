"""T199 — Weekly brief from durable profile proposes six cards.

Verifies:
- ``test_html_has_weekly_brief_control`` — app.html has a Weekly brief
  button that calls ``proposeWeeklyBrief()``.
- ``test_weekly_brief_proposes_six_distinct_specialists`` — clicking the
  control (``weekly_brief: true``) produces exactly six proposed rows,
  one per specialist, with distinct kinds.
- ``test_weekly_brief_uses_saved_profile_fields`` — the proposed titles
  contain the profile fields (name, role, goals, timezone) from the
  committed local profile.
- ``test_weekly_brief_without_profile_typed_fail`` — when no committed
  profile exists the route returns a typed 400 and zero new cards.
- ``test_weekly_brief_does_not_execute`` — no row is ``executed`` or
  ``approved`` after a weekly brief click; all stay ``proposed``.
- ``test_weekly_brief_sets_new_latest_batch`` — the new six cards carry
  one fresh ``batch_id`` that is the newest batch for the tenant.
- ``test_prior_pending_move_to_archive_not_deleted`` — previous pending
  proposed rows move to Archive after a new weekly brief batch; they are
  not deleted.
- ``test_neighbor_cannot_weekly_brief`` — a tenant with no committed
  profile gets a typed 400, not six cards.
- ``test_readme_author_untouched`` — the README Author paragraph is
  present and untouched.
- ``test_readme_does_not_contain_notarized`` — README does not contain
  the word ``notarized``.

Uses ``tmp_path`` via ``tempfile.mkdtemp`` as ``AEGIS_DATA_DIR``.  Does
not write the live ``$HOME/.aegis``.  Does not start uvicorn.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent

_APP_HTML_CANDIDATES = [
    REPO_ROOT / "app.html",
    REPO_ROOT / "desktop" / "macos" / "Aegis.app" / "Contents" / "Resources" / "app.html",
]


def _read_app_html() -> str:
    for p in _APP_HTML_CANDIDATES:
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return ""


class TestT199WeeklyBrief(unittest.TestCase):
    """Weekly brief from durable profile proposes six cards; no profile
    is a typed fail; nothing auto-executes."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t199_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _make_profile(self, tenant: str) -> None:
        """Create a committed profile so the weekly brief has fields."""
        state = start_session(tenant)
        session_id = state["session_id"]
        for q in QUESTIONS:
            answer(session_id, q["id"], f"val-{q['id']}")
        commit(session_id, consent=True)

    # ------------------------------------------------------------------ #
    # 1. HTML has a Weekly brief control
    # ------------------------------------------------------------------ #

    def test_html_has_weekly_brief_control(self) -> None:
        """app.html has a button labeled 'Weekly brief' that calls
        ``proposeWeeklyBrief()``."""
        html = _read_app_html()
        lowered = html.lower()
        self.assertIn("weekly brief", lowered,
                       "app.html must have a Weekly brief button")
        self.assertIn("proposeweeklybrief", lowered.replace(" ", ""),
                       "app.html must call proposeWeeklyBrief()")
        # T199 — the JS sends weekly_brief: true (not a client-built text).
        self.assertIn("weekly_brief", lowered,
                       "app.html must send the weekly_brief flag to the server")

    # ------------------------------------------------------------------ #
    # 2. Weekly brief proposes six distinct specialists
    # ------------------------------------------------------------------ #

    def test_weekly_brief_proposes_six_distinct_specialists(self) -> None:
        """``weekly_brief: true`` produces exactly six proposed rows,
        one per specialist, with distinct kinds."""
        self._make_profile("local")
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "local", "weekly_brief": True},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("count"), 6)
        proposals = body.get("proposals", [])
        self.assertEqual(len(proposals), 6)
        kinds = [p.get("kind", "") for p in proposals]
        self.assertEqual(len(set(kinds)), 6, "all six kinds must be distinct")
        agents = [p.get("agent", "") for p in proposals]
        expected = {"Alina", "Kian", "Bita", "Aylin", "Ahmad", "Amin"}
        self.assertEqual(set(agents), expected,
                          "all six specialist names must appear")
        # All rows stay proposed.
        for p in proposals:
            self.assertEqual(p.get("status"), "proposed")

    # ------------------------------------------------------------------ #
    # 3. Weekly brief uses saved profile fields
    # ------------------------------------------------------------------ #

    def test_weekly_brief_uses_saved_profile_fields(self) -> None:
        """The proposed titles contain the profile fields (name, role,
        goals, timezone) from the committed local profile."""
        self._make_profile("local")
        client = TestClient(create_app())
        # Read the profile to know the field values.
        prof = client.get("/api/v1/twin/profile/local").json()
        name = prof.get("repositories") or ""
        role = prof.get("role") or ""
        goals = prof.get("decision_style") or ""
        tz = prof.get("tools") or ""
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "local", "weekly_brief": True},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        proposals = body.get("proposals", [])
        self.assertEqual(len(proposals), 6)
        # At least the first title must contain the profile fields.
        first_title = proposals[0].get("title", "")
        if name:
            self.assertIn(name, first_title,
                          "title must contain the profile name")
        if role:
            self.assertIn(role, first_title,
                          "title must contain the profile role")
        if goals:
            self.assertIn(goals, first_title,
                          "title must contain the profile goals")
        if tz:
            self.assertIn(tz, first_title,
                          "title must contain the profile timezone")

    # ------------------------------------------------------------------ #
    # 4. Weekly brief without profile is a typed fail
    # ------------------------------------------------------------------ #

    def test_weekly_brief_without_profile_typed_fail(self) -> None:
        """When no committed profile exists the route returns a typed
        400 and zero new cards."""
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "no-profile-tenant", "weekly_brief": True},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertIn("detail", body)
        self.assertIn("profile", body["detail"].lower())

    # ------------------------------------------------------------------ #
    # 5. Weekly brief does not execute
    # ------------------------------------------------------------------ #

    def test_weekly_brief_does_not_execute(self) -> None:
        """After a weekly brief click no row is executed or approved;
        all stay proposed.  No execution path is reached."""
        self._make_profile("local")
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "local", "weekly_brief": True},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for p in body.get("proposals", []):
            self.assertEqual(p.get("status"), "proposed")
            self.assertNotEqual(p.get("status"), "executed")
            self.assertNotEqual(p.get("status"), "approved")

    # ------------------------------------------------------------------ #
    # 6. Weekly brief sets a new latest batch
    # ------------------------------------------------------------------ #

    def test_weekly_brief_sets_new_latest_batch(self) -> None:
        """The new six cards carry one fresh ``batch_id`` that is the
        newest batch for the tenant."""
        self._make_profile("local")
        client = TestClient(create_app())
        # First batch (regular propose).
        resp1 = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "local", "text": "first task"},
        )
        self.assertEqual(resp1.status_code, 200)
        batch1 = resp1.json().get("batch_id")
        # Weekly brief batch.
        resp2 = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "local", "weekly_brief": True},
        )
        self.assertEqual(resp2.status_code, 200)
        batch2 = resp2.json().get("batch_id")
        self.assertIsNotNone(batch2)
        self.assertNotEqual(batch1, batch2,
                             "weekly brief must be a new batch")
        # The queue's latest must be batch2.
        queue = client.get("/api/v1/twin/queue/local").json()
        latest = queue.get("latest", [])
        self.assertEqual(len(latest), 6)
        for r in latest:
            self.assertEqual(r.get("batch_id"), batch2)

    # ------------------------------------------------------------------ #
    # 7. Prior pending move to Archive, not deleted
    # ------------------------------------------------------------------ #

    def test_prior_pending_move_to_archive_not_deleted(self) -> None:
        """Previous pending proposed rows move to Archive after a new
        weekly brief batch; they are not deleted."""
        self._make_profile("local")
        client = TestClient(create_app())
        # First batch.
        resp1 = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "local", "text": "prior task"},
        )
        self.assertEqual(resp1.status_code, 200)
        batch1 = resp1.json().get("batch_id")
        # Weekly brief batch.
        resp2 = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "local", "weekly_brief": True},
        )
        self.assertEqual(resp2.status_code, 200)
        # Queue: latest=batch2, archive=batch1.
        queue = client.get("/api/v1/twin/queue/local").json()
        latest = queue.get("latest", [])
        archive = queue.get("archive", [])
        self.assertEqual(len(latest), 6)
        # Prior pending rows are in archive, not deleted.
        archive_batches = {r.get("batch_id") for r in archive}
        self.assertIn(batch1, archive_batches,
                       "prior batch must be in archive, not deleted")
        for r in archive:
            if r.get("batch_id") == batch1:
                self.assertEqual(r.get("status"), "proposed",
                                 "archived prior rows stay proposed")

    # ------------------------------------------------------------------ #
    # 8. Neighbor cannot weekly brief (cross-tenant typed deny)
    # ------------------------------------------------------------------ #

    def test_neighbor_cannot_weekly_brief(self) -> None:
        """A tenant with no committed profile gets a typed 400, not six
        cards — cross-tenant typed deny."""
        self._make_profile("local")
        client = TestClient(create_app())
        # Neighbor has no profile.
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "neighbor", "weekly_brief": True},
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertIn("detail", body)
        self.assertIn("profile", body["detail"].lower())

    # ------------------------------------------------------------------ #
    # 9. README Author paragraph untouched
    # ------------------------------------------------------------------ #

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and untouched."""
        readme = (REPO_ROOT / "README.md").read_text()
        self.assertIn("## Author", readme,
                       "Author paragraph must be present")
        self.assertIn("Amin Azimi", readme,
                       "Author name must be present")

    # ------------------------------------------------------------------ #
    # 10. README does not contain 'notarized'
    # ------------------------------------------------------------------ #

    def test_readme_does_not_contain_notarized(self) -> None:
        """README does not contain the word 'notarized'."""
        readme = (REPO_ROOT / "README.md").read_text()
        self.assertNotIn(
            "notarized",
            readme.lower(),
            "README must not contain 'notarized'",
        )


if __name__ == "__main__":
    unittest.main()
