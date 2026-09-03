"""T18 — Morning one-page brief from calendar, git, and actions.

Covers:
- render_brief without a consented profile raises ValueError.
- After a T03-style commit + ingest calendar meeting Standup + git repo
  acme/core: file exists, contains "Standup" and "acme/core".
- Headings "Meetings", "Repos", "Pending actions" are present.
- FastAPI 200 on POST /api/v1/twin/brief/morning.
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
from core.twin_morning_brief import render_brief
from fastapi.testclient import TestClient


class TestT18TwinMorningBrief(unittest.TestCase):
    """Morning one-page brief invariants."""

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

    def test_brief_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            render_brief("no_profile_t18")

    def test_brief_contains_standup_and_acme_core(self) -> None:
        self._full_interview("t18a")
        # Ingest a calendar meeting.
        ingest_event(
            "t18a",
            "calendar",
            "meeting",
            {"summary": "Standup", "start": "20260903T090000Z"},
        )
        # Ingest a git commit for repo acme/core.
        ingest_event(
            "t18a",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "aaa", "subject": "feat: init"},
        )

        result = render_brief("t18a")

        # Result shape.
        self.assertEqual(result["tenant_id"], "t18a")
        self.assertIn("path", result)
        self.assertIn("sections", result)

        # File exists on disk.
        brief_path = Path(result["path"])
        self.assertTrue(brief_path.exists(), f"missing file: {brief_path}")

        # File content contains Standup and acme/core.
        text = brief_path.read_text(encoding="utf-8")
        self.assertIn("Standup", text)
        self.assertIn("acme/core", text)

        # Required headings present.
        self.assertIn("## Meetings", text)
        self.assertIn("## Repos", text)
        self.assertIn("## Pending actions", text)

    def test_brief_overwrites_on_second_call(self) -> None:
        self._full_interview("t18b")
        ingest_event(
            "t18b",
            "calendar",
            "meeting",
            {"summary": "Sync", "start": "20260903T100000Z"},
        )

        result1 = render_brief("t18b")
        text1 = Path(result1["path"]).read_text(encoding="utf-8")

        result2 = render_brief("t18b")
        text2 = Path(result2["path"]).read_text(encoding="utf-8")

        self.assertEqual(result1["path"], result2["path"])
        self.assertEqual(text1, text2)

    def test_fastapi_brief_morning_200(self) -> None:
        self._full_interview("t18c")
        ingest_event(
            "t18c",
            "calendar",
            "meeting",
            {"summary": "Review", "start": "20260903T110000Z"},
        )

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/brief/morning",
            json={"tenant_id": "t18c"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t18c")
        self.assertIn("path", body)
        self.assertIn("sections", body)

    def test_fastapi_brief_morning_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/brief/morning",
            json={"tenant_id": "no_profile_t18"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
