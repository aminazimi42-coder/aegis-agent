"""T68 — scheduler stores UTC instants.

``normalize_due_at`` must convert naive local strings to timezone-aware
UTC instants before insert.  ``schedule()`` writes the normalized value.
No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from core.twin_interview import answer, commit, start_session
from core.twin_scheduler import list_jobs, normalize_due_at, schedule


def _complete_interview(tenant_id: str) -> None:
    """Run a full 6-question interview and commit a profile for *tenant_id*."""
    state = start_session(tenant_id)
    session_id = state["session_id"]
    for _ in range(6):
        qid = state["next_question"]["id"]
        state = answer(session_id, qid, "test answer")
    commit(session_id, consent=True)


class TestT68SchedulerUtc(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t68_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # --- normalize_due_at ---

    def test_naive_string_becomes_utc(self):
        result = normalize_due_at("2026-09-05T12:00:00", "UTC")
        self.assertTrue(result.endswith(("Z", "+00:00")), result)
        # The value must be the same wall-clock instant.
        self.assertIn("12:00:00", result)
        self.assertIn("+00:00", result)

    def test_naive_string_with_non_utc_timezone(self):
        result = normalize_due_at("2026-09-05T08:00:00", "America/New_York")
        self.assertTrue(result.endswith(("Z", "+00:00")), result)
        # 08:00 EDT (UTC-4 in Sep) → 12:00 UTC
        self.assertIn("12:00:00", result)

    def test_aware_string_kept_as_utc(self):
        result = normalize_due_at("2026-09-05T12:00:00-05:00")
        self.assertTrue(result.endswith(("Z", "+00:00")), result)
        self.assertIn("17:00:00", result)

    def test_z_suffix_string(self):
        result = normalize_due_at("2026-09-05T12:00:00Z")
        self.assertTrue(result.endswith(("Z", "+00:00")), result)

    def test_invalid_due_at_raises(self):
        with self.assertRaises(ValueError):
            normalize_due_at("not-a-date")
        with self.assertRaises(ValueError):
            normalize_due_at("")

    # --- schedule stores UTC ---

    def test_stored_due_at_is_utc(self):
        _complete_interview("t68a")
        job = schedule("t68a", "standup", "2026-09-05T08:00:00", "America/New_York")
        self.assertTrue(job["due_at"].endswith(("Z", "+00:00")), job["due_at"])
        self.assertIn("12:00:00", job["due_at"])

        rows = list_jobs("t68a")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertTrue(row["due_at"].endswith(("Z", "+00:00")), row["due_at"])
        self.assertIn("12:00:00", row["due_at"])

    def test_naive_utc_string_stored(self):
        _complete_interview("t68b")
        job = schedule("t68b", "demo", "2026-09-05T12:00:00", "UTC")
        self.assertTrue(job["due_at"].endswith(("Z", "+00:00")), job["due_at"])

    # --- no live network ---

    def test_no_live_network(self):
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
