"""T119 — Durable operator profile and session.

Verifies that:
- ``test_profile_survives_new_store``: a committed profile for tenant
  ``local`` survives a process restart — a fresh ``TwinInterviewStore``
  pointing at the same ``AEGIS_DATA_DIR`` reads the same four fields
  (name, role, goals, timezone).
- ``test_html_prefills_from_profile_endpoint``: ``app.html`` fetches
  ``/api/v1/twin/profile/local`` on load and prefills the four operator
  fields when a committed profile exists.
- ``test_start_session_not_auto``: ``app.html`` does NOT auto-click
  Start Session on load — only the button's onclick handler starts a
  session.

No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import (
    QUESTIONS,
    TwinInterviewStore,
    get_last_tenant,
)
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


class TestT119DurableProfile(unittest.TestCase):
    """Durable local operator profile survives process restart."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t119_")
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
    # 1. Profile survives a new store (process restart)
    # ------------------------------------------------------------------ #

    def test_profile_survives_new_store(self) -> None:
        """A committed profile for tenant ``local`` is read by a fresh
        store pointing at the same ``AEGIS_DATA_DIR``."""
        store1 = TwinInterviewStore()
        self._commit_profile(store1, "local")

        # A new store — simulates a process restart against the same db.
        store2 = TwinInterviewStore()
        profile = store2.get_latest_profile("local")
        self.assertIsNotNone(profile, "profile must survive new store")
        assert profile is not None  # for type-checker
        # The four operator-page fields are mapped from the store's
        # six layer fields: name→repositories, role→role,
        # goals→decision_style, timezone→tools.
        self.assertEqual(profile["role"], "val-q_role")
        self.assertEqual(profile["decision_style"], "val-q_decision_style")
        self.assertEqual(profile["tools"], "val-q_tools")
        self.assertEqual(profile["repositories"], "val-q_repos")

        # The session marker must also be durable.
        self.assertEqual(get_last_tenant(), "local")

    # ------------------------------------------------------------------ #
    # 2. app.html prefills from the profile endpoint
    # ------------------------------------------------------------------ #

    def test_html_prefills_from_profile_endpoint(self) -> None:
        """``app.html`` fetches ``/api/v1/twin/profile/local`` on load
        and prefills the four operator fields when a profile exists."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()

        # Must fetch the local profile endpoint on load.
        self.assertIn("profile/local", lowered,
                      "app.html must GET /api/v1/twin/profile/local")
        # Must have a prefill mechanism.
        self.assertIn("prefill", lowered,
                      "app.html must have a prefill mechanism")
        # Must reference all four operator fields.
        self.assertIn("name", lowered)
        self.assertIn("role", lowered)
        self.assertIn("goals", lowered)
        self.assertIn("timezone", lowered)

        # Functional: the API returns the profile for tenant "local".
        store = TwinInterviewStore()
        self._commit_profile(store, "local")
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/twin/profile/local")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNotNone(body.get("profile_id"))
        self.assertEqual(body.get("role"), "val-q_role")

    # ------------------------------------------------------------------ #
    # 3. Start Session is not auto-clicked on load
    # ------------------------------------------------------------------ #

    def test_start_session_not_auto(self) -> None:
        """``app.html`` must NOT call ``startInterview()`` in the init
        block — only the button's ``onclick`` handler may invoke it."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()
        script = lowered.split("<script>", 1)[-1]

        # Find the init block.
        init_idx = script.find("//──init")
        if init_idx == -1:
            init_idx = script.find("// ── init")
        if init_idx == -1:
            init_idx = 0
        init_block = script[init_idx:]

        # The init block must not contain a bare startInterview() call.
        self.assertNotIn(
            "startinterview()",
            init_block.replace(" ", ""),
            "app.html init must not auto-start a session on load",
        )

        # The button onclick must reference startInterview.
        self.assertIn("startinterview", lowered,
                      "Start Session button must call startInterview")


if __name__ == "__main__":
    unittest.main()
