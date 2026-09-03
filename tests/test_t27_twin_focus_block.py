"""T27 — Local focus-block hold (markdown + .ics).

Covers:
- create_block() without a consented profile raises ValueError.
- After a T03 commit, create_block with start=20260903T090000Z:
  both files exist, .ics contains VEVENT and the start string.
- FastAPI 200 on POST /api/v1/twin/focus/block.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_focus_block import create_block
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT27TwinFocusBlock(unittest.TestCase):
    """Focus-block invariants."""

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

    def test_create_block_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            create_block("no_profile_t27", "20260903T090000Z")

    def test_create_block_writes_md_and_ics(self) -> None:
        self._full_interview("t27a")
        result = create_block("t27a", "20260903T090000Z")

        self.assertEqual(result["tenant_id"], "t27a")
        self.assertTrue(Path(result["path_md"]).exists())
        self.assertTrue(Path(result["path_ics"]).exists())

        ics_text = Path(result["path_ics"]).read_text(encoding="utf-8")
        self.assertIn("VEVENT", ics_text)
        self.assertIn("20260903T090000Z", ics_text)

        md_text = Path(result["path_md"]).read_text(encoding="utf-8")
        self.assertIn("Focus", md_text)
        self.assertIn("20260903T090000Z", md_text)

    def test_create_block_invalid_duration_raises(self) -> None:
        self._full_interview("t27b")
        with self.assertRaises(ValueError):
            create_block("t27b", "20260903T090000Z", duration_min=5)

    def test_fastapi_focus_block_200(self) -> None:
        self._full_interview("t27c")
        app = create_app()
        client = TestClient(app)

        resp = client.post(
            "/api/v1/twin/focus/block",
            json={
                "tenant_id": "t27c",
                "start": "20260903T090000Z",
                "duration_min": 90,
                "title": "Focus",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(Path(body["path_md"]).exists())
        self.assertTrue(Path(body["path_ics"]).exists())

    def test_fastapi_focus_block_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)

        resp = client.post(
            "/api/v1/twin/focus/block",
            json={
                "tenant_id": "no_profile_t27_api",
                "start": "20260903T090000Z",
            },
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
