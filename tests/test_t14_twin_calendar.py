"""T14 — Local ICS calendar ingest tests.

Covers:
- ValueError without a consented profile.
- Ingest a tiny .ics with one VEVENT; ingested >= 1; second call ingested == 0.
- FastAPI POST /api/v1/twin/calendar/ics returns 200.
- No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_calendar import ingest_ics
from core.twin_interview import (
    QUESTIONS,
    TwinInterviewStore,
)
from fastapi.testclient import TestClient


class TestT14TwinCalendar(unittest.TestCase):
    """Local ICS calendar ingest invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #

    def _commit_profile(self, tenant_id: str) -> None:
        """Run a full interview and commit a consented profile."""
        store = TwinInterviewStore()
        session = store.start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            store.answer(sid, q["id"], f"ans-{q['id']}")
        store.commit(sid, consent=True)

    def _write_ics(self, path: Path) -> None:
        """Write a tiny .ics file with one VEVENT."""
        path.write_text(
            "BEGIN:VCALENDAR\n"
            "BEGIN:VEVENT\n"
            "SUMMARY:Standup\n"
            "DTSTART:20260903T090000Z\n"
            "END:VEVENT\n"
            "END:VCALENDAR\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ #
    # tests
    # ------------------------------------------------------------------ #

    def test_ingest_without_profile_raises_value_error(self) -> None:
        ics_file = Path(self._tmp) / "cal.ics"
        self._write_ics(ics_file)
        with self.assertRaises(ValueError):
            ingest_ics("t14-noprofile", str(ics_file))

    def test_ingest_ics_one_event_then_dedup(self) -> None:
        self._commit_profile("t14a")
        ics_file = Path(self._tmp) / "cal.ics"
        self._write_ics(ics_file)

        result = ingest_ics("t14a", str(ics_file))
        self.assertEqual(result["tenant_id"], "t14a")
        self.assertGreaterEqual(result["ingested"], 1)

        # Second call should dedup — ingested == 0.
        result2 = ingest_ics("t14a", str(ics_file))
        self.assertEqual(result2["ingested"], 0)

    def test_ingest_ics_not_found_raises(self) -> None:
        self._commit_profile("t14b")
        with self.assertRaises(ValueError):
            ingest_ics("t14b", str(Path(self._tmp) / "nonexistent.ics"))

    def test_fastapi_calendar_ics_200(self) -> None:
        self._commit_profile("t14c")
        ics_file = Path(self._tmp) / "cal.ics"
        self._write_ics(ics_file)

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/calendar/ics",
            json={"tenant_id": "t14c", "ics_path": str(ics_file)},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t14c")
        self.assertGreaterEqual(body["ingested"], 1)


if __name__ == "__main__":
    unittest.main()
