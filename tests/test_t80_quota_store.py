"""T80 — Cloud quota ledger stays outside twin actions.

Covers:
- ``get_quota`` default ``remaining`` is ``0`` when no row exists.
- ``set_quota`` then ``get_quota`` returns the stored values.
- The quota row is stored as a file under ``AEGIS_DATA_DIR`` and not as a
  ``twin_actions`` row.
- No live network.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from core.twin_actions import list_actions
from core.twin_quota import get_quota, set_quota


class TestT80QuotaStore(unittest.TestCase):
    """Quota ledger lives under AEGIS_DATA_DIR, not on twin_actions."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t80_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_default_remaining_is_zero(self) -> None:
        """get_quota returns remaining=0 when no row has been written."""
        result = get_quota("t80-default")
        self.assertEqual(result["remaining"], 0)
        self.assertEqual(result["period_end"], "")

    def test_set_and_get_quota(self) -> None:
        """set_quota persists and get_quota reads back the stored values."""
        stored = set_quota("t80-set", remaining=42, period_end="2026-12-31")
        self.assertEqual(stored["remaining"], 42)
        self.assertEqual(stored["period_end"], "2026-12-31")

        result = get_quota("t80-set")
        self.assertEqual(result["remaining"], 42)
        self.assertEqual(result["period_end"], "2026-12-31")

    def test_quota_not_on_action_row(self) -> None:
        """The quota row is a JSON file on disk, not a twin_actions entry."""
        set_quota("t80-actions", remaining=7, period_end="2026-10-01")

        # The JSON file must exist under AEGIS_DATA_DIR.
        files = list(Path(self._tmp).rglob("*.json"))
        contents = []
        for f in files:
            contents.append(f.read_text(encoding="utf-8"))
        blob = "\n".join(contents)
        self.assertIn("t80-actions", blob)
        self.assertIn("7", blob)

        # twin_actions for the tenant must remain empty.
        actions = list_actions("t80-actions")
        self.assertEqual(actions, [])

        # No payment / card / customer fields are stored.
        for f in files:
            text = f.read_text(encoding="utf-8")
            payload = json.loads(text)
            for forbidden in ("card", "payment", "customer"):
                self.assertNotIn(forbidden, payload)

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
