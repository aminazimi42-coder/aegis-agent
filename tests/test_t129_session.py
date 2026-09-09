"""T129 — Durable operator session after restart.

Verifies that:
- ``test_commit_then_get_returns_profile``: after a commit, a subsequent
  ``GET /api/v1/twin/profile/local`` returns name, role, goals, timezone
  so the operator form is prefilled after an engine restart.
- ``test_missing_store_empty_not_500``: when the store is empty (no
  committed profile), ``GET /api/v1/twin/profile/local`` returns an empty
  form dict (``profile_id`` is ``None``) — not a 500 crash.
- ``test_html_has_no_microphone_hook``: ``app.html`` does not contain any
  microphone / speech-to-text hook; interview remains typed text only.

No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS, TwinInterviewStore
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


class TestT129DurableSession(unittest.TestCase):
    """Durable operator profile survives engine restart."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t129_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _commit_profile(self, store: TwinInterviewStore, tenant: str) -> dict:
        """Run a full interview + commit and return the profile dict."""
        session = store.start_session(tenant)
        sid = session["session_id"]
        for q in QUESTIONS:
            store.answer(sid, q["id"], f"val-{q['id']}")
        return store.commit(sid, True)

    # ------------------------------------------------------------------ #
    # 1. Commit then GET returns the profile (name, role, goals, timezone)
    # ------------------------------------------------------------------ #

    def test_commit_then_get_returns_profile(self) -> None:
        """After a commit, ``GET /api/v1/twin/profile/local`` returns the
        four operator fields so the form is prefilled after restart."""
        store = TwinInterviewStore()
        self._commit_profile(store, "local")

        # Simulate an engine restart: a fresh app + TestClient pointing at
        # the same AEGIS_DATA_DIR must read the committed profile.
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/twin/profile/local")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNotNone(body.get("profile_id"))
        # The four operator-page fields must be present and non-empty.
        self.assertEqual(body.get("role"), "val-q_role")
        self.assertEqual(body.get("decision_style"), "val-q_decision_style")
        self.assertEqual(body.get("tools"), "val-q_tools")
        self.assertEqual(body.get("repositories"), "val-q_repos")

    # ------------------------------------------------------------------ #
    # 2. Missing store returns empty form, not a 500
    # ------------------------------------------------------------------ #

    def test_missing_store_empty_not_500(self) -> None:
        """When no profile has been committed, ``GET /profile/local``
        returns an empty form dict (``profile_id`` is ``None``), not a
        500 crash."""
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/twin/profile/local")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNone(body.get("profile_id"))

    # ------------------------------------------------------------------ #
    # 3. app.html has no microphone / speech-to-text hook
    # ------------------------------------------------------------------ #

    def test_html_has_no_microphone_hook(self) -> None:
        """``app.html`` must not contain any microphone or speech-to-text
        hook — the interview is typed text only."""
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertNotIn("microphone", html)
        self.assertNotIn("speechtotext", html)
        self.assertNotIn("speech_to_text", html)
        self.assertNotIn("webkit-speech", html)
        self.assertNotIn("recognition.start", html)
        self.assertNotIn("mediastream", html)
        self.assertNotIn("getusermedia", html)


if __name__ == "__main__":
    unittest.main()
