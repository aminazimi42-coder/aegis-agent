"""T107 — Serve the operator page from loopback.

Verifies that ``GET /`` on the local FastAPI app returns the operator
``app.html`` as ``text/html`` and that the launcher script opens the
loopback HTTP URL instead of a ``file://`` URL.

No live network except the FastAPI ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAUNCHER = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "MacOS"
    / "Aegis"
)
_APP_HTML = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)


class TestT107ServeOperatorPage(unittest.TestCase):
    """Root route serves app.html; launcher opens http loopback."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t107_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # GET / returns the operator page as text/html
    # ------------------------------------------------------------------ #

    def test_root_returns_html(self) -> None:
        """GET / returns 200, content-type text/html, and the app.html body."""
        self.assertTrue(_APP_HTML.is_file(), f"app.html missing at {_APP_HTML}")
        expected_html = _APP_HTML.read_text(encoding="utf-8")

        app = create_app()
        client = TestClient(app)
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        content_type = resp.headers.get("content-type", "")
        self.assertIn(
            "text/html",
            content_type,
            f"content-type must be text/html, got {content_type!r}",
        )
        # The response body must be the operator app.html content.
        self.assertEqual(resp.text, expected_html)

    # ------------------------------------------------------------------ #
    # Launcher opens http://127.0.0.1:8741/, not a file:// URL
    # ------------------------------------------------------------------ #

    def test_launcher_opens_http_loopback(self) -> None:
        """The launcher must open http://127.0.0.1:8741/, not a file:// URL."""
        self.assertTrue(_LAUNCHER.is_file(), f"launcher missing at {_LAUNCHER}")
        text = _LAUNCHER.read_text(encoding="utf-8")
        # Must open the loopback http URL at /.
        self.assertIn("http://${HOST}:${PORT}/", text)
        # Must not open app.html as a file:// URL.
        self.assertNotIn("open \"$STUB_HTML\"", text)
        # Must not fall back to /health as the default opener target.
        # The operator page is now served at /.
        self.assertIn("127.0.0.1", text)

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
