"""T147 — Operator page entitlement line.

Covers:

* ``test_valid_professional_line_shows_tier``: with a signed,
  valid, tenant-matching ``entitlement.json``, the entitlement API
  route returns ``tier="professional"`` and the operator page HTML
  contains the tier display logic.
* ``test_missing_file_line_is_echo_limited``: with no
  ``entitlement.json`` on disk, the route returns ``tier="echo"`` with
  ``reason="missing_file"`` — the Echo-limited phrase.
* ``test_expired_line_is_echo_limited``: when ``expires_at`` is in
  the past, the route returns ``tier="echo"`` with
  ``reason="expired"`` — the Echo-limited phrase.

No live network except ``TestClient``.  No uvicorn subprocess.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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


class TestT147OperatorEntitlementLine(unittest.TestCase):
    """Operator page shows one honest local entitlement line."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t147_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _signed(self, tenant_id: str, tier: str, expires_at) -> dict:
        """Return an entitlement dict with a valid SHA-256 signature."""
        body = {
            "tenant_id": tenant_id,
            "tier": tier,
            "expires_at": expires_at,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        sig = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        body["signature_sha256"] = sig
        return body

    def _write_entitlement(self, data: dict) -> None:
        """Write *data* as ``entitlement.json`` under ``AEGIS_DATA_DIR``."""
        path = Path(self._tmp) / "entitlement.json"
        path.write_text(json.dumps(data), encoding="utf-8")

    # ------------------------------------------------------------------ #
    # 1) Valid professional — line shows tier
    # ------------------------------------------------------------------ #
    def test_valid_professional_line_shows_tier(self) -> None:
        """A signed, valid, tenant-matching entitlement returns
        ``tier="professional"`` and the HTML contains the tier line."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("t147-tenant", "professional", future)
        self._write_entitlement(data)

        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t147-tenant")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], "professional")
        self.assertIsNone(body["reason"])
        self.assertEqual(body["expires_at"], future)

        # The operator page HTML must contain the entitlement line element.
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("entitlement-line", html)
        self.assertIn("tier", html)

    # ------------------------------------------------------------------ #
    # 2) Missing file — line is Echo-limited
    # ------------------------------------------------------------------ #
    def test_missing_file_line_is_echo_limited(self) -> None:
        """No ``entitlement.json`` on disk → route returns
        ``tier="echo"`` with ``reason="missing_file"``."""
        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t147-missing")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "missing_file")

        # The operator page HTML must contain the Echo-limited phrase.
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("echo-limited", html)

    # ------------------------------------------------------------------ #
    # 3) Expired — line is Echo-limited
    # ------------------------------------------------------------------ #
    def test_expired_line_is_echo_limited(self) -> None:
        """Past ``expires_at`` → route returns ``tier="echo"`` with
        ``reason="expired"``."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        data = self._signed("t147-tenant", "professional", past)
        self._write_entitlement(data)

        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t147-tenant")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "expired")


if __name__ == "__main__":
    unittest.main()
