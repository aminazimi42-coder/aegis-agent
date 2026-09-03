"""T21 — Follow-up list from email and meeting events.

Covers:
- render_followups without a consented profile raises ValueError.
- After a T03-style commit + ingest email subject "Budget review":
  file exists and contains "Budget review".
- After ingest calendar meeting "Standup": file contains "Standup".
- Dedup: second render of the same events yields same count.
- FastAPI 200 on POST /api/v1/twin/followups/render.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_events import ingest_event
from core.twin_followups import render_followups
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT21TwinFollowups(unittest.TestCase):
    """Follow-up list invariants."""

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

    def test_followups_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            render_followups("no_profile_t21")

    def test_followups_contains_budget_review(self) -> None:
        self._full_interview("t21a")
        ingest_event(
            "t21a",
            "email",
            "message",
            {"from": "a@b.com", "subject": "Budget review"},
        )

        result = render_followups("t21a")

        self.assertEqual(result["tenant_id"], "t21a")
        self.assertGreaterEqual(result["count"], 1)

        fpath = Path(result["path"])
        self.assertTrue(fpath.exists(), f"missing file: {fpath}")

        text = fpath.read_text(encoding="utf-8")
        self.assertIn("Budget review", text)

    def test_followups_contains_meeting_summary(self) -> None:
        self._full_interview("t21b")
        ingest_event(
            "t21b",
            "calendar",
            "meeting",
            {"summary": "Standup", "start": "20260903T090000Z"},
        )

        result = render_followups("t21b")
        text = Path(result["path"]).read_text(encoding="utf-8")

        self.assertIn("Standup", text)
        self.assertGreaterEqual(result["count"], 1)

    def test_followups_dedup_same_count(self) -> None:
        self._full_interview("t21c")
        ingest_event(
            "t21c",
            "email",
            "message",
            {"from": "a@b.com", "subject": "Budget review"},
        )
        ingest_event(
            "t21c",
            "calendar",
            "meeting",
            {"summary": "Standup", "start": "20260903T090000Z"},
        )

        result1 = render_followups("t21c")
        result2 = render_followups("t21c")

        self.assertEqual(result1["count"], result2["count"])
        self.assertEqual(result1["count"], 2)

    def test_followups_overwrite_same_path(self) -> None:
        self._full_interview("t21d")
        ingest_event(
            "t21d",
            "email",
            "message",
            {"from": "a@b.com", "subject": "Review"},
        )

        r1 = render_followups("t21d")
        r2 = render_followups("t21d")

        self.assertEqual(r1["path"], r2["path"])

    def test_fastapi_followups_200(self) -> None:
        self._full_interview("t21e")
        ingest_event(
            "t21e",
            "email",
            "message",
            {"from": "a@b.com", "subject": "Budget review"},
        )

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/followups/render",
            json={"tenant_id": "t21e"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t21e")
        self.assertIn("path", body)
        self.assertIn("count", body)
        self.assertGreaterEqual(body["count"], 1)

    def test_fastapi_followups_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/followups/render",
            json={"tenant_id": "no_profile_t21"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
