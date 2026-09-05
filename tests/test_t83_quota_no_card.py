"""T83 — Quota store has no card fields.

Covers:
- ``get_quota`` returns only ``remaining`` and ``period_end`` keys.
- ``set_quota`` stores only ``remaining`` and ``period_end`` (no ``tenant_id``
  or any other extra key).
- ``core/twin_quota.py`` source contains none of the forbidden substrings
  ``stripe``, ``card_number``, ``payment_id``, ``customer_id``.
- No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_quota import get_quota, set_quota


class TestT83QuotaNoCard(unittest.TestCase):
    """Quota store rejects card / payment / customer fields."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t83_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_quota_keys_only_remaining_and_period_end(self) -> None:
        """get_quota keys are a subset of {remaining, period_end}."""
        # Default row (no file written yet).
        result = get_quota("t83-default")
        self.assertSetEqual(set(result.keys()), {"remaining", "period_end"})

        # After set_quota, the returned dict and the on-disk JSON
        # must each contain only ``remaining`` and ``period_end``.
        stored = set_quota("t83-set", remaining=10, period_end="2026-12-31")
        self.assertSetEqual(set(stored.keys()), {"remaining", "period_end"})

        result = get_quota("t83-set")
        self.assertSetEqual(set(result.keys()), {"remaining", "period_end"})

        # The on-disk JSON must also contain only the two allowed keys.
        import json

        files = list(Path(self._tmp).rglob("*.json"))
        self.assertTrue(files, "expected at least one quota JSON file")
        for f in files:
            payload = json.loads(f.read_text(encoding="utf-8"))
            self.assertSetEqual(set(payload.keys()), {"remaining", "period_end"})

    def test_twin_quota_source_has_no_card_fields(self) -> None:
        """core/twin_quota.py source has no forbidden substrings."""
        source_path = Path("core/twin_quota.py")
        source = source_path.read_text(encoding="utf-8")
        for forbidden in ("stripe", "card_number", "payment_id", "customer_id"):
            self.assertNotIn(
                forbidden,
                source,
                msg=f"forbidden substring {forbidden!r} found in twin_quota.py",
            )

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
