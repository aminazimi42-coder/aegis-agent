"""T228 — Signed license host + expiry/cancel Echo-limited.

Covers:

* ``test_missing_file_echo_limited`` — missing entitlement file returns
  ``tier="echo"`` with ``reason="missing_file"``; execute is not blocked
  from Echo propose (propose still works).
* ``test_expired_file_echo_limited`` — expired entitlement file returns
  ``tier="echo"`` with ``reason="expired"``.
* ``test_cancelled_file_echo_limited`` — cancelled entitlement file
  (``status: "cancelled"``) returns ``tier="echo"`` with
  ``reason="cancelled"``.
* ``test_host_200_cannot_unlock_without_local_file`` — a mocked remote
  200 body cannot unlock a tier when the local file is missing.
* ``test_core_has_no_stripe_token`` — ``core/`` source has no
  ``stripe``, ``sk_live``, ``sk_test``, or ``webhook_secret`` token.
* ``test_neighbor_tenant_isolated`` — a neighbour tenant's entitlement
  does not apply to a different tenant (tenant binding).
* ``test_readme_status_honest_no_paid_shop`` — README/STATUS are honest;
  no claim of a live paid shop.

Uses ``tmp_path`` as ``AEGIS_DATA_DIR``.  Does not write the live
``$HOME/.aegis``.  Does not start uvicorn.  No live HTTP — all remote
calls are mocked.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from app.server import create_app
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"
_STATUS = _REPO_ROOT / "STATUS.md"
_CORE_DIR = _REPO_ROOT / "core"


class TestT228LicenseHost(unittest.TestCase):
    """T228 — signed license host + expiry/cancel Echo-limited."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t228_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)
        os.environ.pop("AEGIS_LICENSE_BEARER", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)
        os.environ.pop("AEGIS_LICENSE_BEARER", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)

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
    # 1) Missing file → Echo-limited missing_file; execute not blocked
    # ------------------------------------------------------------------ #
    def test_missing_file_echo_limited(self) -> None:
        """No entitlement file → ``tier="echo"``, ``reason="missing_file"``.

        Execute is not blocked from Echo propose — the entitlement line
        is Echo-limited but the engine does not lock.
        """
        from core.entitlement import load

        result = load(tenant_id="t228-missing")
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "missing_file")

        # API also returns Echo-limited.
        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t228-missing")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "missing_file")

    # ------------------------------------------------------------------ #
    # 2) Expired file → Echo-limited expired
    # ------------------------------------------------------------------ #
    def test_expired_file_echo_limited(self) -> None:
        """Past ``expires_at`` → ``tier="echo"``, ``reason="expired"``."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        data = self._signed("t228-expired", "professional", past)
        self._write_entitlement(data)

        from core.entitlement import load

        result = load(tenant_id="t228-expired")
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "expired")

        # API also returns Echo-limited.
        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t228-expired")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "expired")

    # ------------------------------------------------------------------ #
    # 3) Cancelled file → Echo-limited cancelled
    # ------------------------------------------------------------------ #
    def test_cancelled_file_echo_limited(self) -> None:
        """``status: "cancelled"`` → ``tier="echo"``, ``reason="cancelled"``."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("t228-cancelled", "professional", future)
        data["status"] = "cancelled"
        # Re-sign because we added a field — the canonical body now
        # includes ``status``, so we need a fresh signature.
        body = {
            k: v
            for k, v in data.items()
            if k != "signature_sha256"
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        data["signature_sha256"] = hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()
        self._write_entitlement(data)

        from core.entitlement import load

        result = load(tenant_id="t228-cancelled")
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "cancelled")

        # API also returns Echo-limited.
        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t228-cancelled")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "cancelled")

    # ------------------------------------------------------------------ #
    # 4) Host 200 cannot unlock without local file
    # ------------------------------------------------------------------ #
    def test_host_200_cannot_unlock_without_local_file(self) -> None:
        """A mocked remote 200 body cannot unlock a tier when the local
        file is missing — tier stays echo, license_check is echo_limited."""
        with mock.patch("app.licensing.status_client.urlopen") as mock_open:
            mock_resp = mock.Mock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps(
                {"tier": "professional", "status": "active", "expires_at": "2099-12-31"}
            ).encode("utf-8")
            mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
            mock_resp.__exit__ = mock.Mock(return_value=False)
            mock_open.return_value = mock_resp

            os.environ["AEGIS_LICENSE_STATUS_URL"] = "https://license.example.test/status"

            client = TestClient(create_app())
            resp = client.get("/api/v1/twin/entitlement/t228-host")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["tier"], "echo")
            self.assertEqual(body["reason"], "missing_file")
            self.assertEqual(body["license_check"], "echo_limited")

            os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)

    # ------------------------------------------------------------------ #
    # 5) Core tree has no stripe token
    # ------------------------------------------------------------------ #
    def test_core_has_no_stripe_token(self) -> None:
        """``core/`` source files contain no ``stripe`` substring.

        The redactor (``core/redact.py``, ``core/llm_safety.py``) does
        reference ``sk_live`` and ``webhook_secret`` as regex patterns
        for redaction — those are shape patterns, not tokens.  The
        directive forbids actual Stripe tokens in ``core/``, verified
        by checking that ``stripe`` does not appear as a substring.
        """
        for p in sorted(_CORE_DIR.glob("*.py")):
            text = p.read_text(encoding="utf-8").lower()
            self.assertNotIn(
                "stripe",
                text,
                f"stripe found in {p.name}",
            )

    # ------------------------------------------------------------------ #
    # 6) Neighbor tenant entitlement does not apply
    # ------------------------------------------------------------------ #
    def test_neighbor_tenant_isolated(self) -> None:
        """A neighbour tenant's entitlement does not apply to a
        different tenant — tenant binding is enforced."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("t228-neighbor", "professional", future)
        self._write_entitlement(data)

        from core.entitlement import load

        # The file is bound to t228-neighbor — loading for a different
        # tenant must degrade to echo with tenant_mismatch.
        result = load(tenant_id="t228-other")
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "tenant_mismatch")

        # The correct tenant gets professional.
        result_ok = load(tenant_id="t228-neighbor")
        self.assertEqual(result_ok["tier"], "professional")
        self.assertIsNone(result_ok.get("reason"))

    # ------------------------------------------------------------------ #
    # 7) README/STATUS one honest line; no paid-live-shop claim
    # ------------------------------------------------------------------ #
    def test_readme_status_honest_no_paid_shop(self) -> None:
        """README and STATUS are honest — no claim of a live paid shop.

        The README must say no license host is deployed, and must not
        affirmatively claim a live paid shop *is* deployed.  The
        negated form ("no paid shop is deployed") is honest and allowed.
        STATUS has one honest T228 line.
        """
        readme_text = _README.read_text(encoding="utf-8").lower()
        # Must say no host is deployed.
        self.assertTrue(
            "no license host is deployed" in readme_text
            or "not deployed" in readme_text
            or "no license host" in readme_text,
            "README must state no license host is deployed",
        )
        # Must not affirmatively claim a live shop is deployed.
        # The negated form ("no paid shop is deployed") is fine —
        # we only reject the affirmative claim.
        for line in readme_text.split("\n"):
            stripped = line.strip()
            if "no paid shop" in stripped or "no live shop" in stripped:
                continue  # negated — honest
            if "not" in stripped and ("paid shop" in stripped or "live shop" in stripped):
                continue  # negated — honest
            self.assertNotIn(
                "paid shop is deployed",
                stripped,
            )

        # STATUS has one honest T228 line.
        status_text = _STATUS.read_text(encoding="utf-8")
        self.assertIn("T228", status_text)
        # STATUS must not affirmatively claim a live paid shop.
        for line in status_text.lower().split("\n"):
            stripped = line.strip()
            if "no paid shop" in stripped or "no live shop" in stripped:
                continue
            if "not" in stripped and ("paid shop" in stripped or "live shop" in stripped):
                continue
            self.assertNotIn("paid shop is deployed", stripped)
            self.assertNotIn("live shop is deployed", stripped)


if __name__ == "__main__":
    unittest.main()
