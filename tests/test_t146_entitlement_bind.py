"""T146 — Signed tenant-bound local entitlement bind.

Covers:

* ``test_missing_file_is_echo``: with no ``entitlement.json`` on disk,
  :func:`core.entitlement.load` returns ``tier="echo"`` with a typed
  reason even when a tenant is passed.
* ``test_expired_is_echo``: when ``expires_at`` is in the past,
  :func:`load` returns ``tier="echo"`` even if the tier field reads
  ``professional``, the signature is valid, and the tenant matches.
* ``test_valid_signed_professional_reads_tier``: a well-formed
  ``entitlement.json`` with ``tenant_id``, ``tier="professional"``,
  a future ``expires_at``, and a matching ``signature_sha256`` yields
  ``tier="professional"`` from :func:`load`.
* ``test_mutated_body_is_echo``: a file whose body has been altered after
  signing (so ``signature_sha256`` no longer matches the canonical body)
  degrades to ``echo``.
* ``test_foreign_tenant_is_echo``: a valid file whose ``tenant_id`` does
  not match the caller's tenant degrades to ``echo``.

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

from core.entitlement import ECHO_TIER, load


class TestT146EntitlementBind(unittest.TestCase):
    """Signed tenant-bound local entitlement — bind, mismatch, mutate."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t146_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _write_entitlement(self, data: dict) -> None:
        """Write *data* as ``entitlement.json`` under ``AEGIS_DATA_DIR``."""
        path = Path(self._tmp) / "entitlement.json"
        path.write_text(json.dumps(data), encoding="utf-8")

    def _signed(
        self,
        tenant_id: str,
        tier: str,
        expires_at,
    ) -> dict:
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

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #
    def test_missing_file_is_echo(self) -> None:
        """No entitlement.json on disk → tier is echo with a typed reason."""
        result = load(tenant_id="t146-tenant")
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(result["reason"], "missing_file")

    def test_expired_is_echo(self) -> None:
        """Past expires_at → tier falls back to echo even with valid sig."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        data = self._signed("t146-tenant", "professional", past)
        self._write_entitlement(data)
        result = load(tenant_id="t146-tenant")
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(result["reason"], "expired")

    def test_valid_signed_professional_reads_tier(self) -> None:
        """Valid signed entitlement with matching tenant → professional."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("t146-tenant", "professional", future)
        self._write_entitlement(data)
        result = load(tenant_id="t146-tenant")
        self.assertEqual(result["tier"], "professional")

    def test_mutated_body_is_echo(self) -> None:
        """Altered body after signing → signature mismatch → echo."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("t146-tenant", "professional", future)
        # Mutate the body *after* signing so the signature no longer
        # matches the canonical body.
        data["tier"] = "echo"
        self._write_entitlement(data)
        result = load(tenant_id="t146-tenant")
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(result["reason"], "signature_mismatch")

    def test_foreign_tenant_is_echo(self) -> None:
        """Valid file whose tenant_id differs from caller → echo."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("other-tenant", "professional", future)
        self._write_entitlement(data)
        result = load(tenant_id="t146-tenant")
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(result["reason"], "tenant_mismatch")


if __name__ == "__main__":
    unittest.main()
