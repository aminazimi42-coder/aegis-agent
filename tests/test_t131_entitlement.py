"""T131 — Local entitlement file only.

Covers:

* ``test_missing_file_is_echo``: with no ``entitlement.json`` on disk,
  :func:`core.entitlement.load` returns ``tier="echo"`` and
  :func:`core.entitlement.current_tier` returns ``"echo"``.
* ``test_expired_is_echo``: when ``expires_at`` is in the past,
  :func:`load` returns ``tier="echo"`` even if the tier field reads
  ``professional`` and the signature is valid.
* ``test_valid_professional_reads_tier``: a well-formed
  ``entitlement.json`` with ``tier="professional"``, a future
  ``expires_at``, and a matching ``signature_sha256`` yields
  ``tier="professional"`` from both :func:`load` and
  :func:`current_tier`.

No live network except ``TestClient``.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from core.entitlement import ECHO_TIER, current_tier, load


class TestT131Entitlement(unittest.TestCase):
    """Local entitlement file — missing, expired, and valid rows."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t131_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    def _write_entitlement(self, data: dict) -> None:
        """Write *data* as ``entitlement.json`` under ``AEGIS_DATA_DIR``."""
        from pathlib import Path

        path = Path(self._tmp) / "entitlement.json"
        path.write_text(json.dumps(data), encoding="utf-8")

    def _signed(self, tier: str, expires_at) -> dict:
        """Return a minimal entitlement dict with a valid signature."""
        body = {"tier": tier, "expires_at": expires_at}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        sig = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        body["signature_sha256"] = sig
        return body

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #
    def test_missing_file_is_echo(self) -> None:
        """No entitlement.json on disk → tier is echo."""
        result = load()
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(current_tier(), ECHO_TIER)

    def test_expired_is_echo(self) -> None:
        """Past expires_at → tier falls back to echo even with valid sig."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        data = self._signed("professional", past)
        self._write_entitlement(data)
        result = load()
        self.assertEqual(result["tier"], ECHO_TIER)

    def test_valid_professional_reads_tier(self) -> None:
        """Valid entitlement.json with professional tier and future expiry."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("professional", future)
        self._write_entitlement(data)
        result = load()
        self.assertEqual(result["tier"], "professional")
        self.assertEqual(current_tier(), "professional")


if __name__ == "__main__":
    unittest.main()
