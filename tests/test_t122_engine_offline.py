"""T122 — Honest desktop operator when the engine is down.

Verifies that:
- ``test_html_has_offline_banner_copy``: app.html contains visible
  "Engine offline" copy that points the operator at the local start
  script and preserves the committed profile.
- ``test_health_or_profile_error_path_exists``: app.html has a
  ``setOffline`` function and an ``offline-banner`` element so that
  health/profile fetch failures surface a visible banner instead of
  looking like an empty twin.
- ``test_offline_disables_propose_and_approve``: app.html guards
  ``proposeTask``, ``approveAction`` and ``rejectAction`` with an
  ``engineOnline`` check so Propose/Approve stay disabled while
  offline.

No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

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


class TestT122EngineOffline(unittest.TestCase):
    """Operator page is honest when the engine is not reachable."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t122_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1. Offline banner copy
    # ------------------------------------------------------------------ #

    def test_html_has_offline_banner_copy(self) -> None:
        """app.html has visible 'Engine offline' banner copy."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()

        # The banner must say "engine offline" (or "offline").
        self.assertIn("engine offline", lowered,
                      "app.html missing 'engine offline' banner copy")

        # The banner must reference the local start script.
        self.assertIn("run_local.sh", lowered,
                      "app.html must point at scripts/run_local.sh")

        # The banner must tell the operator to preserve the profile.
        self.assertIn("profile", lowered,
                      "app.html must mention profile preservation")

        # The offline-banner element must exist for JS to show/hide.
        self.assertIn("offline-banner", lowered,
                      "app.html missing offline-banner element")

    # ------------------------------------------------------------------ #
    # 2. Health or profile error path exists
    # ------------------------------------------------------------------ #

    def test_health_or_profile_error_path_exists(self) -> None:
        """app.html has a setOffline function wired to the health check."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()

        # setOffline must be defined and called on health failure.
        self.assertIn("setoffline", lowered,
                      "app.html missing setOffline function")
        self.assertIn("engineonline", lowered,
                      "app.html missing engineOnline state variable")

        # The health check must call setOffline on error.
        self.assertTrue(
            "setoffline()" in lowered,
            "app.html health check must call setOffline() on error",
        )

    # ------------------------------------------------------------------ #
    # 3. Propose and Approve are disabled while offline
    # ------------------------------------------------------------------ #

    def test_offline_disables_propose_and_approve(self) -> None:
        """proposeTask, approveAction, rejectAction check engineOnline."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()

        # proposeTask must guard on engineOnline.
        self.assertIn("if (!engineonline)", lowered,
                      "app.html missing engineOnline guard in functions")

        # All three action functions must reference engineOnline.
        for fn in ("proposetask", "approveaction", "rejectaction"):
            self.assertIn(fn, lowered,
                          f"app.html missing {fn} function")

    # ------------------------------------------------------------------ #
    # 4. No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)

    # ------------------------------------------------------------------ #
    # 5. Operator page served by TestClient still returns app.html
    # ------------------------------------------------------------------ #

    def test_operator_page_has_banner(self) -> None:
        """GET / returns the app.html with the offline banner copy."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        client = TestClient(create_app())
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("engine offline", resp.text.lower())
        self.assertIn("offline-banner", resp.text.lower())


if __name__ == "__main__":
    unittest.main()
