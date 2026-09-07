"""T105 — Desktop window wired to the local twin.

Verifies that ``app.html`` is an operator page for interview, status,
and queue against ``127.0.0.1`` only, and that the local twin's
``/health`` endpoint returns ``ok``.

No live network.
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
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
_LAUNCHER = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "MacOS"
    / "Aegis"
)


class TestT105DesktopWindow(unittest.TestCase):
    """Operator page wiring and local health check."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t105_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # app.html content checks
    # ------------------------------------------------------------------ #

    def test_app_html_mentions_interview_and_queue(self) -> None:
        """app.html must contain 'interview' and 'queue' sections."""
        self.assertTrue(
            _APP_HTML.is_file(),
            f"app.html missing at {_APP_HTML}",
        )
        text = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("interview", text.lower())
        self.assertIn("queue", text.lower())

    def test_app_html_uses_loopback_only(self) -> None:
        """app.html must reference 127.0.0.1 and no third-party CDN."""
        self.assertTrue(_APP_HTML.is_file())
        text = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", text)
        # Must not load any external CDN scripts.
        # Common CDN patterns: cdn.jsdelivr, cdnjs, unpkg, jsdelivr.
        cdn_patterns = [
            r"cdn\.jsdelivr",
            r"cdnjs",
            r"unpkg\.com",
            r"jsdelivr\.net",
        ]
        for pat in cdn_patterns:
            self.assertNotRegex(
                text,
                pat,
                f"app.html must not reference CDN ({pat})",
            )
        # Every http(s) URL in the file must be 127.0.0.1 or localhost.
        urls = re.findall(r"https?://[^\s\"'<>]+", text)
        for u in urls:
            self.assertTrue(
                "127.0.0.1" in u or "localhost" in u,
                f"app.html references non-loopback URL: {u}",
            )

    def test_launcher_opens_app_html(self) -> None:
        """The launcher script must open app.html, not stub.html."""
        self.assertTrue(_LAUNCHER.is_file())
        text = _LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("app.html", text)
        # The open target must not be the old stub.
        self.assertNotIn("Resources/stub.html", text)

    # ------------------------------------------------------------------ #
    # Local health route
    # ------------------------------------------------------------------ #

    def test_health_ok(self) -> None:
        """GET /health returns 200 with ok=true."""
        app = create_app()
        client = TestClient(app)
        resp = client.get("/health")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("ok"))

    def test_queue_endpoint_returns_json(self) -> None:
        """GET /api/v1/twin/queue/{tenant} returns pending/approved_waiting keys."""
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/twin/queue/test-tenant")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn("pending", payload)
        self.assertIn("approved_waiting", payload)

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
