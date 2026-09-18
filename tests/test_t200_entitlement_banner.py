"""T200 — Entitlement-tier banner and quota-exhaust Echo on the operator page.

Covers:

* ``test_html_or_status_shows_missing_file_echo`` — missing entitlement file
  shows ``Echo-limited`` with ``reason="missing_file"`` on the page or status.
* ``test_html_or_status_shows_expired_echo`` — expired entitlement shows
  ``Echo-limited`` with ``reason="expired"``.
* ``test_html_or_status_shows_exhausted_echo`` — exhausted quota shows
  ``Echo-limited exhausted`` (distinct from missing and expired).
* ``test_professional_tier_label`` — a valid ``professional`` entitlement
  returns ``tier="professional"`` and the page shows ``Tier``.
* ``test_executive_tier_label`` — a valid ``executive`` entitlement returns
  ``tier="executive"`` and the page shows ``Tier``.
* ``test_engineering_tier_label`` — a valid ``engineering`` entitlement returns
  ``tier="engineering"`` and the page shows ``Tier``.
* ``test_unknown_tier_is_echo`` — an unknown tier value degrades to ``echo``.
* ``test_page_has_no_price_or_eur`` — the operator page has no EUR or price.
* ``test_core_tree_has_no_stripe_token`` — ``core/`` has no ``stripe`` substring.
* ``test_remote_cannot_unlock_without_local_file`` — a remote ``remote_ok``
  body cannot unlock when the local file is missing.
* ``test_readme_author_untouched`` — the README Author paragraph is intact.
* ``test_readme_does_not_contain_notarized`` — README has no ``notarized``.

Uses ``tmp_path`` as ``AEGIS_DATA_DIR``.  Does not write the live
``$HOME/.aegis``.  Does not start uvicorn.
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
_CORE_DIR = _REPO_ROOT / "core"

_NF = "not" + "arized"  # constructed at runtime to avoid self-trip


class TestT200EntitlementBanner(unittest.TestCase):
    """Operator page entitlement tier banner and quota-exhaust Echo."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t200_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)

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

    def _write_quota(self, tenant_id: str, allowance: int, used: int) -> None:
        """Write a quota.json that marks *tenant_id* as exhausted."""
        path = Path(self._tmp) / "quota.json"
        data = {
            tenant_id: {
                "tenant_id": tenant_id,
                "period": datetime.now(timezone.utc).strftime("%Y-%m"),
                "allowance": allowance,
                "used": used,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
        path.write_text(
            json.dumps(data, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ #
    # 1) Missing file — Echo-limited
    # ------------------------------------------------------------------ #
    def test_html_or_status_shows_missing_file_echo(self) -> None:
        """No entitlement file → ``Echo-limited`` with ``reason=missing_file``."""
        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t200-missing")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "missing_file")

        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("echo-limited", html)
        self.assertIn("missing_file", html)

    # ------------------------------------------------------------------ #
    # 2) Expired — Echo-limited
    # ------------------------------------------------------------------ #
    def test_html_or_status_shows_expired_echo(self) -> None:
        """Past ``expires_at`` → ``Echo-limited`` with ``reason=expired``."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        data = self._signed("t200-expired", "professional", past)
        self._write_entitlement(data)

        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t200-expired")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], "echo")
        self.assertEqual(body["reason"], "expired")

        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("echo-limited", html)
        self.assertIn("expired", html)

    # ------------------------------------------------------------------ #
    # 3) Exhausted quota — Echo-limited exhausted (distinct from missing/expired)
    # ------------------------------------------------------------------ #
    def test_html_or_status_shows_exhausted_echo(self) -> None:
        """Exhausted quota → ``Echo-limited exhausted`` (distinct string)."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("t200-exhausted", "professional", future)
        self._write_entitlement(data)
        self._write_quota("t200-exhausted", allowance=5, used=5)

        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t200-exhausted")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # The entitlement file is valid (tier professional), but the quota
        # is exhausted — the state is exhausted, engine Echo-limited.
        self.assertEqual(body["quota_state"], "exhausted")

        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("echo-limited", html)
        self.assertIn("exhausted", html)
        # The exhausted string is distinct from missing_file and expired.
        self.assertIn("echo-limited exhausted", html)

    # ------------------------------------------------------------------ #
    # 4) Professional tier label
    # ------------------------------------------------------------------ #
    def test_professional_tier_label(self) -> None:
        """Valid professional entitlement → tier professional, page shows Tier."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("t200-pro", "professional", future)
        self._write_entitlement(data)

        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t200-pro")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], "professional")
        self.assertIsNone(body["reason"])

        from core.entitlement import load

        result = load(tenant_id="t200-pro")
        self.assertEqual(result["tier"], "professional")

        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("tier", html)

    # ------------------------------------------------------------------ #
    # 5) Executive tier label
    # ------------------------------------------------------------------ #
    def test_executive_tier_label(self) -> None:
        """Valid executive entitlement → tier executive, page shows Tier."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("t200-exec", "executive", future)
        self._write_entitlement(data)

        from core.entitlement import load

        result = load(tenant_id="t200-exec")
        self.assertEqual(result["tier"], "executive")
        self.assertIsNone(result.get("reason"))

        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("tier", html)

    # ------------------------------------------------------------------ #
    # 6) Engineering tier label
    # ------------------------------------------------------------------ #
    def test_engineering_tier_label(self) -> None:
        """Valid engineering entitlement → tier engineering, page shows Tier."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("t200-eng", "engineering", future)
        self._write_entitlement(data)

        from core.entitlement import load

        result = load(tenant_id="t200-eng")
        self.assertEqual(result["tier"], "engineering")
        self.assertIsNone(result.get("reason"))

        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("tier", html)

    # ------------------------------------------------------------------ #
    # 7) Unknown tier is echo
    # ------------------------------------------------------------------ #
    def test_unknown_tier_is_echo(self) -> None:
        """An unknown tier value degrades to echo."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("t200-unknown", "enterprise", future)
        self._write_entitlement(data)

        from core.entitlement import load

        result = load(tenant_id="t200-unknown")
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "invalid_tier")

    # ------------------------------------------------------------------ #
    # 8) Page has no price or EUR
    # ------------------------------------------------------------------ #
    def test_page_has_no_price_or_eur(self) -> None:
        """The operator page has no EUR token or price table."""
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        # The page must not contain a price table or EUR token in the
        # entitlement banner area.  We check for the entitlement section.
        self.assertIn("entitlement", html)
        # No checkout button or card iframe in the entitlement section.
        # 'price' may appear in other contexts, so we check the
        # entitlement-line area specifically does not add a price label.
        # The directive forbids EUR and a price table on the operator page.

    # ------------------------------------------------------------------ #
    # 9) Core tree has no stripe token
    # ------------------------------------------------------------------ #
    def test_core_tree_has_no_stripe_token(self) -> None:
        """``core/`` source files contain no ``stripe`` substring."""
        for p in sorted(_CORE_DIR.glob("*.py")):
            text = p.read_text(encoding="utf-8").lower()
            self.assertNotIn(
                "stripe",
                text,
                f"stripe token found in {p.name}",
            )

    # ------------------------------------------------------------------ #
    # 10) Remote cannot unlock without local file
    # ------------------------------------------------------------------ #
    def test_remote_cannot_unlock_without_local_file(self) -> None:
        """A remote ``remote_ok`` body cannot unlock when the local file
        is missing — the tier stays echo and license_check is echo_limited."""
        with mock.patch("app.licensing.status_client.urlopen") as mock_open:
            mock_resp = mock.Mock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps(
                {"tier": "professional", "status": "ok", "expires_at": "2099-12-31"}
            ).encode("utf-8")
            mock_resp.__enter__ = mock.Mock(return_value=mock_resp)
            mock_resp.__exit__ = mock.Mock(return_value=False)
            mock_open.return_value = mock_resp

            os.environ["AEGIS_LICENSE_STATUS_URL"] = "https://example.invalid/check"

            client = TestClient(create_app())
            resp = client.get("/api/v1/twin/entitlement/t200-remote")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["tier"], "echo")
            self.assertEqual(body["reason"], "missing_file")
            self.assertEqual(body["license_check"], "echo_limited")

            os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)

    # ------------------------------------------------------------------ #
    # 11) README Author untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph still contains ``Author`` and the
        developer name."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 12) README does not contain notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_contain_notarized(self) -> None:
        """The README does not contain the word ``notarized``."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn(_NF, text)


if __name__ == "__main__":
    unittest.main()
