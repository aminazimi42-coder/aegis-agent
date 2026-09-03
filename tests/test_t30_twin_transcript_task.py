"""T30 — Transcript file to a proposed twin action.

Covers:
- from_transcript without a consented profile raises ValueError.
- from_transcript with a missing transcript file raises ValueError.
- After a T03 commit, transcript "Call the Berlin hotel tonight":
  markdown contains "Berlin hotel" and a non-empty action_id.
- FastAPI 200 on POST /api/v1/twin/transcript/task.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_transcript_task import from_transcript
from fastapi.testclient import TestClient


class TestT30TwinTranscriptTask(unittest.TestCase):
    """Transcript-to-proposed-action invariants."""

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

    def test_from_transcript_without_profile_raises_value_error(self) -> None:
        transcript = Path(self._tmp) / "t.txt"
        transcript.write_text("Call the Berlin hotel tonight", encoding="utf-8")
        with self.assertRaises(ValueError):
            from_transcript("no_profile_t30", str(transcript))

    def test_from_transcript_missing_file_raises_value_error(self) -> None:
        self._full_interview("t30b")
        with self.assertRaises(ValueError):
            from_transcript("t30b", str(Path(self._tmp) / "nonexistent.txt"))

    def test_from_transcript_writes_berlin_hotel(self) -> None:
        self._full_interview("t30c")
        transcript = Path(self._tmp) / "meeting.txt"
        transcript.write_text(
            "Call the Berlin hotel tonight\n"
            "Other notes here\n",
            encoding="utf-8",
        )

        result = from_transcript("t30c", str(transcript))

        self.assertEqual(result["tenant_id"], "t30c")
        self.assertTrue(result["action_id"])
        self.assertEqual(result["title"], "Call the Berlin hotel tonight")

        md_path = Path(result["path"])
        self.assertTrue(md_path.exists())
        text = md_path.read_text(encoding="utf-8")
        self.assertIn("Berlin hotel", text)
        self.assertIn(result["action_id"], text)

    def test_from_transcript_title_clipped_to_80(self) -> None:
        self._full_interview("t30d")
        long_line = "x" * 120
        transcript = Path(self._tmp) / "long.txt"
        transcript.write_text(long_line + "\n", encoding="utf-8")

        result = from_transcript("t30d", str(transcript))

        self.assertEqual(len(result["title"]), 80)
        self.assertTrue(result["action_id"])

    def test_from_transcript_overwrites_on_second_call(self) -> None:
        self._full_interview("t30e")
        transcript = Path(self._tmp) / "chat.txt"
        transcript.write_text("First action\n", encoding="utf-8")

        result1 = from_transcript("t30e", str(transcript))
        md_path = Path(result1["path"])
        text1 = md_path.read_text(encoding="utf-8")
        self.assertIn("First action", text1)

        transcript.write_text("Second action\n", encoding="utf-8")
        from_transcript("t30e", str(transcript))
        text2 = md_path.read_text(encoding="utf-8")
        self.assertIn("Second action", text2)
        self.assertNotIn("First action", text2)

    def test_fastapi_transcript_task_200(self) -> None:
        self._full_interview("t30f")
        transcript = Path(self._tmp) / "api.txt"
        transcript.write_text(
            "Call the Berlin hotel tonight\n",
            encoding="utf-8",
        )

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/transcript/task",
            json={
                "tenant_id": "t30f",
                "transcript_path": str(transcript),
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t30f")
        self.assertTrue(body["action_id"])
        self.assertIn("Berlin hotel", body["title"])
        text = Path(body["path"]).read_text(encoding="utf-8")
        self.assertIn("Berlin hotel", text)

    def test_fastapi_transcript_task_400_without_profile(self) -> None:
        transcript = Path(self._tmp) / "no_profile.txt"
        transcript.write_text("hello\n", encoding="utf-8")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/transcript/task",
            json={
                "tenant_id": "no_profile_t30_api",
                "transcript_path": str(transcript),
            },
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
