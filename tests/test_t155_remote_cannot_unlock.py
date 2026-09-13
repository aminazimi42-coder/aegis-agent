"""T155 — Remote license-status body cannot unlock without a local file.

Covers:

* ``test_missing_local_file_ignores_professional_remote_body`` — when
  the local entitlement file is absent, a mocked remote body that says
  ``{tier: professional, status: ok, expires_at: far future}`` must
  leave the tenant Echo-limited (``tier="echo"``, ``reason``, and
  ``license_check="echo_limited"``).
* ``test_expired_local_file_ignores_remote_ok`` — when the local file is
  expired, a mocked ``remote_ok`` body does not lift the tier.
* ``test_foreign_tenant_local_file_ignores_remote_ok`` — when the local
  file is valid but bound to a different tenant, a mocked ``remote_ok``
  body does not lift the tier.
* ``test_broken_hmac_ignores_remote_ok`` — when the local file has a
  bad HMAC signature, a mocked ``remote_ok`` body does not lift the
  tier.
* ``test_valid_local_file_keeps_local_tier_if_remote_disagrees`` — when
  the local file is valid and unexpired, the local tier wins even if
  the remote body claims a lower or different tier.
* ``test_propose_execute_still_do_not_import_status_client`` — the
  ``propose`` and ``execute`` code paths still do not import or call
  ``app.licensing.status_client``.

All HTTP is mocked via ``unittest.mock.patch`` on
``app.licensing.status_client.urlopen``.  No uvicorn subprocess, no
public host, no real network socket.
"""

from __future__ import annotations

import hashlib
import hmac
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
from core.entitlement import ECHO_TIER, load
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


def _signed_entitlement(
    tenant_id: str,
    tier: str,
    expires_at,
    *,
    issuer: str | None = None,
    key: str = "",
) -> dict:
    """Return an entitlement dict with a valid SHA-256 or HMAC signature."""
    body: dict = {
        "tenant_id": tenant_id,
        "tier": tier,
        "expires_at": expires_at,
    }
    if issuer is not None:
        body["issuer"] = issuer
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    if issuer == "local-cli":
        sig = hmac.new(
            key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    else:
        sig = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    body["signature_sha256"] = sig
    return body


class TestT155RemoteCannotUnlock(unittest.TestCase):
    """Remote license-status body cannot unlock without local file."""

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
        self._tmp = tempfile.mkdtemp(prefix="aegis_t155_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        for key, val in self._saved.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)

    def _write_entitlement(self, data: dict) -> None:
        path = Path(self._tmp) / "entitlement.json"
        path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _remote_body(
        self, tier: str = "professional", expires_at: str | None = None
    ) -> bytes:
        if expires_at is None:
            future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
            expires_at = future
        return json.dumps(
            {"tier": tier, "expires_at": expires_at, "status": "ok"}
        ).encode()

    def _entitlement_api(self, tenant_id: str = "t155-tenant") -> dict:
        """Call the operator entitlement API with a mocked remote."""
        os.environ["AEGIS_LICENSE_STATUS_URL"] = "https://license.example.test/status"
        remote_body = self._remote_body()
        with patch(
            "app.licensing.status_client.urlopen",
            return_value=_FakeResponse(200, remote_body),
        ):
            client = TestClient(create_app())
            resp = client.get(f"/api/v1/twin/entitlement/{tenant_id}")
            self.assertEqual(resp.status_code, 200)
            return resp.json()

    # ------------------------------------------------------------------ #
    # 1) Missing local file ignores professional remote body
    # ------------------------------------------------------------------ #
    def test_missing_local_file_ignores_professional_remote_body(self) -> None:
        """No entitlement.json on disk; a mocked remote body that says
        ``professional`` must leave the tenant Echo-limited."""
        body = self._entitlement_api("t155-tenant")
        self.assertEqual(body["tier"], ECHO_TIER)
        self.assertEqual(body["reason"], "missing_file")
        self.assertEqual(body["license_check"], "echo_limited")
        self.assertNotIn("remote_tier", body)
        # Verify no file was written by the remote body.
        self.assertFalse((Path(self._tmp) / "entitlement.json").is_file())

    # ------------------------------------------------------------------ #
    # 2) Expired local file ignores remote OK
    # ------------------------------------------------------------------ #
    def test_expired_local_file_ignores_remote_ok(self) -> None:
        """An expired local file stays Echo-limited even when the
        remote body says ``status: ok`` with a far-future expiry."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        data = _signed_entitlement("t155-tenant", "professional", past)
        self._write_entitlement(data)
        result = load(tenant_id="t155-tenant")
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(result["reason"], "expired")

        body = self._entitlement_api("t155-tenant")
        self.assertEqual(body["tier"], ECHO_TIER)
        self.assertEqual(body["reason"], "expired")
        self.assertEqual(body["license_check"], "echo_limited")

    # ------------------------------------------------------------------ #
    # 3) Foreign tenant local file ignores remote OK
    # ------------------------------------------------------------------ #
    def test_foreign_tenant_local_file_ignores_remote_ok(self) -> None:
        """A valid local file bound to a different tenant stays
        Echo-limited even when the remote body says ``ok``."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = _signed_entitlement("other-tenant", "professional", future)
        self._write_entitlement(data)
        result = load(tenant_id="t155-tenant")
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(result["reason"], "tenant_mismatch")

        body = self._entitlement_api("t155-tenant")
        self.assertEqual(body["tier"], ECHO_TIER)
        self.assertEqual(body["reason"], "tenant_mismatch")
        self.assertEqual(body["license_check"], "echo_limited")

    # ------------------------------------------------------------------ #
    # 4) Broken HMAC ignores remote OK
    # ------------------------------------------------------------------ #
    def test_broken_hmac_ignores_remote_ok(self) -> None:
        """A local file with a tampered HMAC signature stays Echo-limited
        even when the remote body says ``ok``."""
        key = "test-issuer-secret-t155-broken"
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = key
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = _signed_entitlement(
            "t155-tenant", "professional", future, issuer="local-cli", key=key
        )
        # Tamper with the signature after signing.
        data["signature_sha256"] = "0" * 64
        self._write_entitlement(data)

        body = self._entitlement_api("t155-tenant")
        self.assertEqual(body["tier"], ECHO_TIER)
        self.assertEqual(body["reason"], "signature_mismatch")
        self.assertEqual(body["license_check"], "echo_limited")

    # ------------------------------------------------------------------ #
    # 5) Valid local file keeps local tier if remote disagrees
    # ------------------------------------------------------------------ #
    def test_valid_local_file_keeps_local_tier_if_remote_disagrees(self) -> None:
        """When the local file is valid and unexpired, the local tier
        wins even if the remote body claims a different tier."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = _signed_entitlement("t155-tenant", "professional", future)
        self._write_entitlement(data)
        result = load(tenant_id="t155-tenant")
        self.assertEqual(result["tier"], "professional")

        # Remote body says "echo" but local says "professional".
        os.environ["AEGIS_LICENSE_STATUS_URL"] = "https://license.example.test/status"
        remote_body = self._remote_body(tier="echo")
        with patch(
            "app.licensing.status_client.urlopen",
            return_value=_FakeResponse(200, remote_body),
        ):
            client = TestClient(create_app())
            resp = client.get("/api/v1/twin/entitlement/t155-tenant")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
        self.assertEqual(body["tier"], "professional")
        self.assertIsNone(body["reason"])
        # Remote can only confirm or report unreachable — local tier wins.
        self.assertNotEqual(body["tier"], "echo")

    # ------------------------------------------------------------------ #
    # 6) Propose and execute still do not import status_client
    # ------------------------------------------------------------------ #
    def test_propose_execute_still_do_not_import_status_client(self) -> None:
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
    # 7) README has the cannot-unlock sentence
    # ------------------------------------------------------------------ #
    def test_readme_says_remote_cannot_unlock(self) -> None:
        """README must say a remote body cannot unlock without a local
        file."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertIn("cannot unlock", text)
        self.assertIn("remote", text)
        self.assertIn("missing", text)
        self.assertNotIn("stripe", text)


if __name__ == "__main__":
    unittest.main()
