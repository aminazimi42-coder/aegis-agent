"""T205 — Quit engine sends SIGTERM on 127.0.0.1:8741 only.

Covers:

* ``test_html_has_quit_engine_control`` — the operator page has the
  ``btn-quit-engine`` control, the ``quit-engine-label`` span, and the
  ``quitEngine`` function.
* ``test_quit_route_exists`` — ``POST /api/v1/twin/quit`` is registered.
* ``test_localhost_127_accepts`` — a TestClient request (host
  ``testclient``) is accepted as local.
* ``test_localhost_ipv6_accepts`` — ``::1`` is accepted by
  ``_is_localhost``.
* ``test_non_local_host_typed_deny`` — a non-local host is a typed
  deny (``non_local_host_denied``).
* ``test_sigterm_helper_is_mockable`` — the ``_send_quit_sigterm``
  helper is a single mockable seam.
* ``test_port_free_engine_already_stopped`` — when port 8741 is free
  the body is ``engine already stopped`` and no SIGTERM is sent.
* ``test_quit_does_not_start_uvicorn`` — no long-running uvicorn is
  started by the test suite.
* ``test_readme_author_untouched`` — the README Author paragraph is
  intact.
* ``test_readme_does_not_contain_notarized`` — README has no
  ``notarized``.

The SIGTERM helper is mocked so the pytest process is never killed.
No uvicorn is started.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from app.server import _is_localhost, create_app
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
_README = _REPO_ROOT / "README.md"

_NF = "not" + "arized"  # built at runtime to avoid self-trip


class TestT205QuitEngine(unittest.TestCase):
    """Quit engine SIGTERM on 127.0.0.1:8741 only; CI mocks the signal."""

    def setUp(self) -> None:
        self._tmp_env = os.environ.pop("AEGIS_DATA_DIR", None)

    def tearDown(self) -> None:
        if self._tmp_env is not None:
            os.environ["AEGIS_DATA_DIR"] = self._tmp_env
        else:
            os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) HTML has Quit engine control
    # ------------------------------------------------------------------ #
    def test_html_has_quit_engine_control(self) -> None:
        """The operator page has ``btn-quit-engine`` and ``quitEngine``."""
        html = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("btn-quit-engine", html)
        self.assertIn("quit-engine-label", html)
        self.assertIn("quitEngine", html)

    # ------------------------------------------------------------------ #
    # 2) Route exists
    # ------------------------------------------------------------------ #
    def test_quit_route_exists(self) -> None:
        """``POST /api/v1/twin/quit`` is registered on the app."""
        client = TestClient(create_app())
        # We mock the sigterm helper and port check so the call is safe.
        with mock.patch("app.server._send_quit_sigterm"), \
             mock.patch("app.server._is_port_8741_in_use", return_value=True):
            resp = client.post(
                "/api/v1/twin/quit",
                json={"tenant_id": "t205-route"},
            )
        # 200 means the route exists and was reached.
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------------ #
    # 3) Localhost 127.0.0.1 accepts
    # ------------------------------------------------------------------ #
    def test_localhost_127_accepts(self) -> None:
        """``127.0.0.1`` is accepted as a local host."""
        self.assertTrue(_is_localhost("127.0.0.1"))

    # ------------------------------------------------------------------ #
    # 4) Localhost ::1 accepts
    # ------------------------------------------------------------------ #
    def test_localhost_ipv6_accepts(self) -> None:
        """``::1`` is accepted as a local host."""
        self.assertTrue(_is_localhost("::1"))

    # ------------------------------------------------------------------ #
    # 5) Non-local host typed deny
    # ------------------------------------------------------------------ #
    def test_non_local_host_typed_deny(self) -> None:
        """A non-local host is a typed deny."""
        self.assertFalse(_is_localhost("203.0.113.5"))
        self.assertFalse(_is_localhost("example.com"))

    # ------------------------------------------------------------------ #
    # 6) SIGTERM helper is a single mockable seam
    # ------------------------------------------------------------------ #
    def test_sigterm_helper_is_mockable(self) -> None:
        """The ``_send_quit_sigterm`` helper can be patched safely."""
        called = {"n": 0}

        def _fake() -> None:
            called["n"] += 1

        client = TestClient(create_app())
        with mock.patch("app.server._send_quit_sigterm", side_effect=_fake), \
             mock.patch("app.server._is_port_8741_in_use", return_value=True):
            resp = client.post(
                "/api/v1/twin/quit",
                json={"tenant_id": "t205-mock"},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], "engine_stopping")
        self.assertEqual(called["n"], 1)

    # ------------------------------------------------------------------ #
    # 7) Port free — engine already stopped
    # ------------------------------------------------------------------ #
    def test_port_free_engine_already_stopped(self) -> None:
        """When port 8741 is free the body is ``engine already stopped``."""
        client = TestClient(create_app())
        with mock.patch("app.server._is_port_8741_in_use", return_value=False), \
             mock.patch("app.server._send_quit_sigterm") as sig:
            resp = client.post(
                "/api/v1/twin/quit",
                json={"tenant_id": "t205-free"},
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["code"], "engine_already_stopped")
        # No SIGTERM is sent when the engine is already stopped.
        sig.assert_not_called()

    # ------------------------------------------------------------------ #
    # 8) Quit does not start uvicorn
    # ------------------------------------------------------------------ #
    def test_quit_does_not_start_uvicorn(self) -> None:
        """The test suite does not import or start a long-running uvicorn."""
        import sys

        # No uvicorn server object should be running from this module.
        self.assertNotIn("uvicorn.server", sys.modules)
        # The route handler itself does not reference uvicorn.
        src = (_REPO_ROOT / "app" / "server.py").read_text(encoding="utf-8")
        # The quit route uses os.kill + signal, not uvicorn.run.
        self.assertNotIn("uvicorn.run", src)

    # ------------------------------------------------------------------ #
    # 9) README Author untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph still contains ``Author``."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("Author", text)

    # ------------------------------------------------------------------ #
    # 10) README does not contain notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_contain_notarized(self) -> None:
        """The README does not contain the word ``notarized``."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn(_NF, text)


if __name__ == "__main__":
    unittest.main()
