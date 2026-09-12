"""T151 — Optional labeled HTTP license-status client.

Covers:

* ``test_unset_url_does_not_open_socket`` — when
  ``AEGIS_LICENSE_STATUS_URL`` is unset/empty, the function returns
  ``{"license_check": "local_only"}`` and never opens a socket.
* ``test_unreachable_url_returns_echo_limited_or_unreachable`` — on
  timeout, DNS, TLS, or non-200, the function returns
  ``{"license_check": "remote_unreachable"}``.
* ``test_propose_and_execute_modules_do_not_import_status_client`` —
  the ``propose`` and ``execute`` paths must not import the status
  client.
* ``test_remote_ok_cannot_unlock_without_local_file`` — when the remote
  returns ``remote_ok`` but the local file is missing, the entitlement
  API still returns ``tier="echo"`` with a ``reason`` (i.e. the remote
  cannot unlock a tier).
* ``test_readme_names_optional_license_url`` — README mentions
  ``AEGIS_LICENSE_STATUS_URL``.

No live HTTP, no uvicorn subprocess, no public host.  All HTTP is mocked
via ``unittest.mock.patch`` on ``urllib.request.urlopen``.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.server import create_app
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"


class _FakeResponse:
    """Minimal context-manager response for mocking urlopen."""

    def __init__(self, status_code: int = 200, body: bytes = b"{}"):
        self.status = status_code
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


class TestT151LicenseStatusClient(unittest.TestCase):
    """Optional labeled HTTP license-status client."""

    def setUp(self) -> None:
        # Persist env var state so tests don't leak.
        self._saved = {
            k: os.environ.get(k)
            for k in ("AEGIS_LICENSE_STATUS_URL", "AEGIS_LICENSE_BEARER", "AEGIS_DATA_DIR")
        }
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)
        os.environ.pop("AEGIS_LICENSE_BEARER", None)
        self._tmp = tempfile.mkdtemp(prefix="aegis_t151_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        for key, val in self._saved.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    # ------------------------------------------------------------------ #
    # 1) Unset URL does not open a socket
    # ------------------------------------------------------------------ #
    def test_unset_url_does_not_open_socket(self) -> None:
        """When ``AEGIS_LICENSE_STATUS_URL`` is unset, return
        ``local_only`` without calling ``urlopen``."""
        from app.licensing.status_client import check_remote_status

        with patch("urllib.request.urlopen") as mock_urlopen:
            result = check_remote_status()
            self.assertEqual(result["license_check"], "local_only")
            mock_urlopen.assert_not_called()

        # Also test empty string.
        os.environ["AEGIS_LICENSE_STATUS_URL"] = ""
        with patch("urllib.request.urlopen") as mock_urlopen:
            result = check_remote_status()
            self.assertEqual(result["license_check"], "local_only")
            mock_urlopen.assert_not_called()

    # ------------------------------------------------------------------ #
    # 2) Unreachable URL returns remote_unreachable
    # ------------------------------------------------------------------ #
    def test_unreachable_url_returns_echo_limited_or_unreachable(self) -> None:
        """On timeout, DNS, TLS, or non-200, return
        ``remote_unreachable``."""
        from urllib.error import URLError

        from app.licensing.status_client import check_remote_status

        os.environ["AEGIS_LICENSE_STATUS_URL"] = "https://license.example.test/status"

        # 2a — URLError (DNS / connection refused)
        with patch("app.licensing.status_client.urlopen", side_effect=URLError("dns fail")):
            result = check_remote_status()
            self.assertEqual(result["license_check"], "remote_unreachable")

        # 2b — TimeoutError
        with patch("app.licensing.status_client.urlopen", side_effect=TimeoutError("timed out")):
            result = check_remote_status()
            self.assertEqual(result["license_check"], "remote_unreachable")

        # 2c — OSError (generic)
        with patch("app.licensing.status_client.urlopen", side_effect=OSError("broken pipe")):
            result = check_remote_status()
            self.assertEqual(result["license_check"], "remote_unreachable")

        # 2d — non-200 status
        with patch(
            "app.licensing.status_client.urlopen",
            return_value=_FakeResponse(503, b'{"tier": "professional"}'),
        ):
            result = check_remote_status()
            self.assertEqual(result["license_check"], "remote_unreachable")

        # 2e — 200 but malformed JSON
        with patch(
            "app.licensing.status_client.urlopen",
            return_value=_FakeResponse(200, b"not json"),
        ):
            result = check_remote_status()
            self.assertEqual(result["license_check"], "remote_unreachable")

        # 2f — 200 but not a dict
        with patch(
            "app.licensing.status_client.urlopen",
            return_value=_FakeResponse(200, b'"a string"'),
        ):
            result = check_remote_status()
            self.assertEqual(result["license_check"], "remote_unreachable")

    # ------------------------------------------------------------------ #
    # 3) Propose and execute modules do not import status_client
    # ------------------------------------------------------------------ #
    def test_propose_and_execute_modules_do_not_import_status_client(self) -> None:
        """Neither the ``propose`` path nor the ``execute`` path may
        import or call ``app.licensing.status_client``."""
        # Check that none of the modules that handle propose/execute
        # import the status_client module.
        propose_execute_modules = [
            "core.twin_actions",
        ]
        for mod_name in propose_execute_modules:
            # Ensure the module is loaded.
            if mod_name in sys.modules:
                mod = sys.modules[mod_name]
            else:
                mod = importlib.import_module(mod_name)
            mod_path = mod.__file__ or ""
            self.assertTrue(mod_path, f"{mod_name} has no __file__")
            source = open(mod_path, encoding="utf-8").read()
            self.assertNotIn(
                "status_client",
                source,
                f"{mod_name} must not import or reference status_client",
            )
            self.assertNotIn(
                "AEGIS_LICENSE_STATUS_URL",
                source,
                f"{mod_name} must not reference AEGIS_LICENSE_STATUS_URL",
            )

    # ------------------------------------------------------------------ #
    # 4) Remote OK cannot unlock without local file
    # ------------------------------------------------------------------ #
    def test_remote_ok_cannot_unlock_without_local_file(self) -> None:
        """When the remote returns ``remote_ok`` but the local file is
        missing, the entitlement API returns ``tier="echo"`` with a
        reason — the remote must not unlock a tier."""
        os.environ["AEGIS_LICENSE_STATUS_URL"] = "https://license.example.test/status"

        # No entitlement.json in the temp dir — local is missing.
        remote_body = json.dumps(
            {"tier": "professional", "expires_at": None, "status": "active"}
        ).encode()

        with patch(
            "app.licensing.status_client.urlopen",
            return_value=_FakeResponse(200, remote_body),
        ):
            client = TestClient(create_app())
            resp = client.get("/api/v1/twin/entitlement/t151-tenant")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            # Local file is missing — tier stays echo.
            self.assertEqual(body["tier"], "echo")
            self.assertEqual(body["reason"], "missing_file")
            # Remote reported OK, but since local is Echo-limited, the
            # license_check is echo_limited (not a tier unlock).
            self.assertEqual(body["license_check"], "echo_limited")

    # ------------------------------------------------------------------ #
    # 5) README names optional license URL
    # ------------------------------------------------------------------ #
    def test_readme_names_optional_license_url(self) -> None:
        """README must mention ``AEGIS_LICENSE_STATUS_URL``."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("AEGIS_LICENSE_STATUS_URL", text)


if __name__ == "__main__":
    unittest.main()
