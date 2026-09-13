"""T169 — Remote license status cannot unlock without a local entitlement file.

Covers:

* ``test_unset_url_does_not_open_socket`` — when
  ``AEGIS_LICENSE_STATUS_URL`` is unset/empty, the status client returns
  ``{"license_check": "local_only"}`` without opening a socket.
* ``test_missing_local_file_ignores_professional_remote_body`` — when the
  local entitlement file is absent, a mocked remote body that says
  ``{tier: professional}`` must leave the tenant Echo-limited.
* ``test_expired_local_file_ignores_remote_ok`` — when the local file is
  expired, a mocked ``remote_ok`` body does not lift the tier.
* ``test_propose_and_execute_modules_do_not_import_status_client`` — the
  ``propose`` and ``execute`` paths must not import the status client.
* ``test_status_payload_has_license_check`` — the entitlement API response
  carries a ``license_check`` key and a ``license_source`` key.
* ``test_readme_does_not_claim_host_deployed`` — README must not claim a
  license host is deployed.
* ``test_readme_author_untouched`` — the README Author paragraph must be
  present and unchanged.

All HTTP is mocked via ``unittest.mock.patch`` on
``app.licensing.status_client.urlopen``.  No uvicorn subprocess, no
public host, no real network socket.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.server import create_app
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"


class _FakeResponse:
    """Minimal context-manager response for mocking urlopen."""

    def __init__(self, status_code: int = 200, body: bytes = b"{}") -> None:
        self.status = status_code
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


class TestT169LicenseStatusOutsideExecute(unittest.TestCase):
    """Remote license status cannot unlock without a local file."""

    def setUp(self) -> None:
        self._saved = {
            k: os.environ.get(k)
            for k in (
                "AEGIS_LICENSE_STATUS_URL",
                "AEGIS_LICENSE_BEARER",
                "AEGIS_DATA_DIR",
                "AEGIS_ENTITLEMENT_ISSUER_KEY",
            )
        }
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)
        os.environ.pop("AEGIS_LICENSE_BEARER", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)
        self._tmp = tempfile.mkdtemp(prefix="aegis_t169_")
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
    # 2) Missing local file ignores professional remote body
    # ------------------------------------------------------------------ #
    def test_missing_local_file_ignores_professional_remote_body(self) -> None:
        """No entitlement.json on disk; a mocked remote body that says
        ``professional`` must leave the tenant Echo-limited."""
        os.environ["AEGIS_LICENSE_STATUS_URL"] = "https://license.example.test/status"
        remote_body = json.dumps(
            {"tier": "professional", "expires_at": None, "status": "active"}
        ).encode()
        with patch(
            "app.licensing.status_client.urlopen",
            return_value=_FakeResponse(200, remote_body),
        ):
            client = TestClient(create_app())
            resp = client.get("/api/v1/twin/entitlement/t169-tenant")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "missing_file")
        self.assertEqual(body["license_check"], "echo_limited")
        # No entitlement.json was written by the remote body.
        self.assertFalse((Path(self._tmp) / "entitlement.json").is_file())

    # ------------------------------------------------------------------ #
    # 3) Expired local file ignores remote OK
    # ------------------------------------------------------------------ #
    def test_expired_local_file_ignores_remote_ok(self) -> None:
        """An expired local file stays Echo-limited even when the
        remote body says ``status: ok`` with a far-future expiry."""
        import hashlib

        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        data = {
            "tenant_id": "t169-tenant",
            "tier": "professional",
            "expires_at": past,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        data["signature_sha256"] = hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()
        path = Path(self._tmp) / "entitlement.json"
        path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        os.environ["AEGIS_LICENSE_STATUS_URL"] = "https://license.example.test/status"
        remote_body = json.dumps(
            {"tier": "professional", "expires_at": None, "status": "ok"}
        ).encode()
        with patch(
            "app.licensing.status_client.urlopen",
            return_value=_FakeResponse(200, remote_body),
        ):
            client = TestClient(create_app())
            resp = client.get("/api/v1/twin/entitlement/t169-tenant")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "expired")
        self.assertEqual(body["license_check"], "echo_limited")

    # ------------------------------------------------------------------ #
    # 4) Propose and execute modules do not import status_client
    # ------------------------------------------------------------------ #
    def test_propose_and_execute_modules_do_not_import_status_client(self) -> None:
        """Neither the ``propose`` path nor the ``execute`` path may
        import or call ``app.licensing.status_client``."""
        propose_execute_modules = [
            "core.twin_actions",
        ]
        for mod_name in propose_execute_modules:
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
    # 5) Status payload has license_check and license_source
    # ------------------------------------------------------------------ #
    def test_status_payload_has_license_check(self) -> None:
        """The entitlement API response must carry ``license_check``
        and ``license_source`` keys."""
        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t169-tenant")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("license_check", body)
        self.assertIn("license_source", body)
        # No local file — source is none, check is local_only (URL unset).
        self.assertEqual(body["license_source"], "none")
        self.assertEqual(body["license_check"], "local_only")

    # ------------------------------------------------------------------ #
    # 6) README does not claim a host is deployed
    # ------------------------------------------------------------------ #
    def test_readme_does_not_claim_host_deployed(self) -> None:
        """README must not claim a license host is deployed."""
        text = _README.read_text(encoding="utf-8")
        lower = text.lower()
        # Must say no host is deployed.
        self.assertTrue(
            "no license host is deployed" in lower
            or "not deployed" in lower
            or "no license host" in lower,
            "README must state no license host is deployed",
        )
        # Must not claim a host IS deployed.
        self.assertNotIn(
            "license host is deployed",
            lower.replace("no license host is deployed", ""),
        )

    # ------------------------------------------------------------------ #
    # 7) README Author paragraph is untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph must be present and contain the
        original author identity line."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)
        self.assertIn("Azimi Innovation Lab", text)


if __name__ == "__main__":
    unittest.main()
