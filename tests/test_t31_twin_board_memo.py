"""T31 — Board weekly memo from digest, meetings, and decisions.

Covers:
- render_memo() without a consented profile raises ValueError.
- After a T03 commit + ingest calendar "Standup": board_memo.md
  contains "Standup".
- FastAPI 200 on POST /api/v1/twin/memo/board.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_board_memo import render_memo
from core.twin_events import ingest_event
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT31TwinBoardMemo(unittest.TestCase):
    """Board-memo invariants."""

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

    def test_render_memo_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            render_memo("no_profile_t31")

    def test_render_memo_contains_standup(self) -> None:
        self._full_interview("t31a")
        ingest_event(
            tenant_id="t31a",
            source="calendar",
            kind="meeting",
            payload={"summary": "Standup", "start": "20260903T090000Z"},
        )

        result = render_memo("t31a")

        self.assertEqual(result["tenant_id"], "t31a")
        memo_path = Path(result["path"])
        self.assertTrue(memo_path.exists())

        text = memo_path.read_text(encoding="utf-8")
        self.assertIn("Standup", text)
        self.assertIn("## Meetings", text)
        self.assertIn("## Repos", text)
        self.assertIn("## Decisions", text)
        self.assertIn("Do not act on this memo without written board approval.", text)

    def test_render_memo_includes_weekly_digest(self) -> None:
        self._full_interview("t31b")
        wp_dir = Path(self._tmp) / "work_products" / "t31b"
        wp_dir.mkdir(parents=True, exist_ok=True)
        (wp_dir / "weekly_digest.md").write_text(
            "# Weekly Digest\n\nHighlights from the week.\n",
            encoding="utf-8",
        )

        result = render_memo("t31b")
        text = Path(result["path"]).read_text(encoding="utf-8")

        self.assertIn("## Weekly Digest", text)
        self.assertIn("Highlights from the week.", text)

    def test_render_memo_includes_voice_from_style_lock(self) -> None:
        self._full_interview("t31c")
        wp_dir = Path(self._tmp) / "work_products" / "t31c"
        wp_dir.mkdir(parents=True, exist_ok=True)
        (wp_dir / "style_lock.md").write_text(
            "# Style Lock\n\n## Voice Notes\n\n- Keep it short.\n"
            "- Active voice.\n- No jargon.\n- Be direct.\n"
            "- Extra line 7.\n- Extra line 8.\n- Line 9 not included.\n",
            encoding="utf-8",
        )

        result = render_memo("t31c")
        text = Path(result["path"]).read_text(encoding="utf-8")

        self.assertIn("## Voice", text)
        self.assertIn("Keep it short.", text)
        # Only first 8 lines are copied; line 9 should not appear.
        self.assertNotIn("Line 9 not included.", text)

    def test_render_memo_overwrites_on_second_call(self) -> None:
        self._full_interview("t31d")
        ingest_event(
            tenant_id="t31d",
            source="calendar",
            kind="meeting",
            payload={"summary": "Sprint Review", "start": "20260905T100000Z"},
        )

        render_memo("t31d")
        path = (
            Path(self._tmp) / "work_products" / "t31d" / "board_memo.md"
        )
        text1 = path.read_text(encoding="utf-8")
        self.assertIn("Sprint Review", text1)

        # Second call should still produce a valid file.
        render_memo("t31d")
        text2 = path.read_text(encoding="utf-8")
        self.assertIn("Sprint Review", text2)

    def test_fastapi_board_memo_200(self) -> None:
        self._full_interview("t31e")
        ingest_event(
            tenant_id="t31e",
            source="calendar",
            kind="meeting",
            payload={"summary": "Board Standup", "start": "20260903T090000Z"},
        )

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/memo/board",
            json={"tenant_id": "t31e"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t31e")
        text = Path(body["path"]).read_text(encoding="utf-8")
        self.assertIn("Board Standup", text)

    def test_fastapi_board_memo_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/memo/board",
            json={"tenant_id": "no_profile_t31"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
