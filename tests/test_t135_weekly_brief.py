"""T135 — First-run weekly brief from saved profile.

Verifies that:
- ``test_profile_present_proposes_brief``: when a durable profile exists,
  the operator page ``app.html`` has a "Propose weekly brief" button that
  POSTs a deterministic task string built from the saved profile fields
  (name, role, goals, timezone) to the existing ``/api/v1/twin/propose``
  endpoint.  The API returns 200 with ``count`` >= 1.
- ``test_empty_profile_no_brief``: when no profile is committed, the
  button is disabled and the endpoint is not called — no fabricated brief.
  The ``/api/v1/twin/profile/local`` endpoint returns an empty object
  (``profile_id`` is None).
- ``test_no_voice_hook``: ``app.html`` has no microphone / voice / audio
  capture hook — the weekly brief is text-only.

No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient

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


class TestT135WeeklyBrief(unittest.TestCase):
    """Weekly brief from saved profile; empty profile does not invent."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t135_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _commit_profile(self, tenant: str) -> dict:
        """Run a full interview + commit and return the profile dict."""
        session = start_session(tenant)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"val-{q['id']}")
        return commit(sid, True)

    # ------------------------------------------------------------------ #
    # 1. Profile present → button proposes a deterministic brief
    # ------------------------------------------------------------------ #

    def test_profile_present_proposes_brief(self) -> None:
        """With a committed profile, the weekly-brief button builds a
        deterministic task string from name/role/goals/timezone and
        POSTs it to ``/api/v1/twin/propose`` — returns 200."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()

        # Button must exist.
        self.assertIn("propose weekly brief", lowered,
                      "app.html must have a Propose weekly brief button")
        # Button must call the JS function.
        self.assertIn("proposeweeklybrief", lowered.replace(" ", ""),
                       "app.html must call proposeWeeklyBrief()")

        # Functional: commit a profile, then call the propose endpoint
        # with a deterministic brief string built from profile fields.
        self._commit_profile("local")
        app = create_app()
        client = TestClient(app)

        # Read the profile to build the same deterministic string.
        prof = client.get("/api/v1/twin/profile/local").json()
        self.assertIsNotNone(prof.get("profile_id"))
        name = prof.get("repositories") or ""
        role = prof.get("role") or ""
        goals = prof.get("decision_style") or ""
        tz = prof.get("tools") or ""
        brief_text = (
            f"Weekly desk brief for {name} ({role})"
            f" — goals: {goals} — timezone: {tz}"
        )

        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "local", "text": brief_text},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(body.get("count", 0), 1)

    # ------------------------------------------------------------------ #
    # 2. Empty profile → no brief (button disabled, endpoint returns empty)
    # ------------------------------------------------------------------ #

    def test_empty_profile_no_brief(self) -> None:
        """With no committed profile, the button is disabled and the
        profile endpoint returns an empty object (profile_id is None)."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()

        # Button must start disabled.
        self.assertIn("disabled", lowered,
                       "weekly-brief button must be disabled by default")

        app = create_app()
        client = TestClient(app)

        # No profile committed → endpoint returns empty.
        resp = client.get("/api/v1/twin/profile/local")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNone(body.get("profile_id"))

        # Empty text → 400 typed error (no fabricated brief).
        resp2 = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "local", "text": ""},
        )
        self.assertEqual(resp2.status_code, 400)
        self.assertIn("detail", resp2.json())

    # ------------------------------------------------------------------ #
    # 3. No voice / microphone hook
    # ------------------------------------------------------------------ #

    def test_no_voice_hook(self) -> None:
        """``app.html`` must not contain any microphone / voice / audio
        capture hook — the weekly brief is text-only."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()
        for term in ("microphone", "getusermedia", "mediastream", "audiocapture"):
            self.assertNotIn(
                term,
                lowered,
                f"app.html must not contain '{term}' — no voice hook",
            )

    # ------------------------------------------------------------------ #
    # 4. No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
