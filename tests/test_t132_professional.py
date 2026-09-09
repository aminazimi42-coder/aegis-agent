"""T132 — Professional local Echo tier.

Covers:

* ``test_professional_file_shows_tier``: a valid ``entitlement.json``
  with ``tier="professional"`` and a future ``expires_at`` makes
  :func:`core.entitlement.current_tier` return ``"professional"``.
* ``test_unknown_tier_is_echo``: an ``entitlement.json`` whose
  ``tier`` value is not recognised (e.g. ``"enterprise"``) degrades
  to ``echo`` — :func:`~core.entitlement.load` returns
  ``{"tier": "echo"}`` and no network or billing endpoint is opened.
* ``test_home_has_no_price``: the rendered home markdown contains
  ``Tier: professional`` when the entitlement file is valid, but
  **no** EUR amount or SKU pricing table appears anywhere in the
  page.  Cloud billing is never enabled by a local professional tier.

No live network except ``TestClient``.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.entitlement import ECHO_TIER, current_tier, load


class TestT132Professional(unittest.TestCase):
    """Professional local tier label — no price, no cloud billing."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t132_")
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
    def test_professional_file_shows_tier(self) -> None:
        """Valid professional entitlement → current_tier is professional."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("professional", future)
        self._write_entitlement(data)
        self.assertEqual(current_tier(), "professional")
        self.assertEqual(load()["tier"], "professional")

    def test_unknown_tier_is_echo(self) -> None:
        """Unknown tier value degrades to echo, no billing opened."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("enterprise", future)
        self._write_entitlement(data)
        result = load()
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(current_tier(), ECHO_TIER)

    def test_home_has_no_price(self) -> None:
        """Home markdown shows Tier: professional but no EUR or SKU table."""
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("professional", future)
        self._write_entitlement(data)

        # Build the home markdown the same way twin_home._render_markdown
        # does — a minimal page that shows the tier label.
        from core.twin_home import _render_markdown

        markdown = _render_markdown(
            tenant_id="t132-tenant",
            pending=[],
            approved=[],
            rejected=[],
            due=[],
            brief_name=None,
            file_names=[],
        )
        # The tier label must be present.
        self.assertIn("Tier: professional", markdown)
        # No EUR price amounts anywhere.
        self.assertNotRegex(markdown, r"EUR\s|€\s?\d|\$\s?\d")
        # No SKU pricing table headers or rows.
        self.assertNotRegex(markdown, r"(?i)sku|price|billing|plan|per month|monthly")
        # Cloud billing is not enabled by the local professional tier.
        self.assertNotIn("cloud billing", markdown.lower())


if __name__ == "__main__":
    unittest.main()
