"""T20 — Meeting briefs from calendar events and repos.

Covers:
- render_meetings without a consented profile raises ValueError.
- After a T03-style commit + ingest calendar meeting Standup:
  file exists and contains "Standup".
- Each meeting section has summary, start, repos, and 3 prep bullets.
- FastAPI 200 on POST /api/v1/twin/brief/meetings.
- Overwrite on each call.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_events import ingest_event
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_meeting_brief import render_meetings
from fastapi.testclient import TestClient


class TestT20TwinMeetingBrief(unittest.TestCase):
    """Meeting briefs invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete T03 interview and return the session id."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_render_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            render_meetings("no_profile_t20")

    def test_meeting_brief_contains_standup(self) -> None:
        self._full_interview("t20a")
        ingest_event(
            "t20a",
            "calendar",
            "meeting",
            {"summary": "Standup", "start": "20260903T090000Z"},
        )
        ingest_event(
            "t20a",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "aaa", "subject": "feat: init"},
        )

        result = render_meetings("t20a")

        self.assertEqual(result["tenant_id"], "t20a")
        self.assertEqual(result["count"], 1)

        brief_path = Path(result["path"])
        self.assertTrue(brief_path.exists(), f"missing file: {brief_path}")

        text = brief_path.read_text(encoding="utf-8")
        self.assertIn("Standup", text)

    def test_meeting_section_has_prep_bullets_and_repos(self) -> None:
        self._full_interview("t20b")
        ingest_event(
            "t20b",
            "calendar",
            "meeting",
            {"summary": "Sprint Review", "start": "20260903T140000Z"},
        )
        ingest_event(
            "t20b",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "bbb", "subject": "fix: bug"},
        )

        result = render_meetings("t20b")
        text = Path(result["path"]).read_text(encoding="utf-8")

        self.assertIn("Sprint Review", text)
        self.assertIn("acme/core", text)
        self.assertIn("**Prep:**", text)
        # At least 3 prep bullets.
        self.assertGreaterEqual(text.count("- "), 3)

    def test_overwrite_on_second_call(self) -> None:
        self._full_interview("t20c")
        ingest_event(
            "t20c",
            "calendar",
            "meeting",
            {"summary": "Sync", "start": "20260903T100000Z"},
        )

        result1 = render_meetings("t20c")
        text1 = Path(result1["path"]).read_text(encoding="utf-8")

        result2 = render_meetings("t20c")
        text2 = Path(result2["path"]).read_text(encoding="utf-8")

        self.assertEqual(result1["path"], result2["path"])
        self.assertEqual(text1, text2)

    def test_fastapi_brief_meetings_200(self) -> None:
        self._full_interview("t20d")
        ingest_event(
            "t20d",
            "calendar",
            "meeting",
            {"summary": "Review", "start": "20260903T110000Z"},
        )

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/brief/meetings",
            json={"tenant_id": "t20d"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t20d")
        self.assertIn("path", body)
        self.assertIn("count", body)

    def test_fastapi_brief_meetings_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/brief/meetings",
            json={"tenant_id": "no_profile_t20"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
