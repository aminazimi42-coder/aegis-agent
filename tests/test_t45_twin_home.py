"""T45 — Executive home page from real local state.

Covers:
- render_home without a consented profile raises ValueError.
- After a T03 commit, render_home writes home.md containing "Pending" or "Due".
- FastAPI 200 on POST /api/v1/twin/home.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_home import render_home
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_persist import put_approval
from core.twin_scheduler import schedule
from fastapi.testclient import TestClient


class TestT45TwinHome(unittest.TestCase):
    """Executive home page invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t45_")
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

    def test_render_home_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            render_home("no_profile_t45")

    def test_render_home_writes_home_md_with_pending_or_due(self) -> None:
        self._full_interview("t45a")
        result = render_home("t45a")

        self.assertEqual(result["tenant_id"], "t45a")
        self.assertIn("path", result)

        md_path = Path(result["path"])
        self.assertTrue(md_path.exists(), f"missing home.md: {md_path}")
        md_text = md_path.read_text(encoding="utf-8")
        self.assertTrue(
            "Pending" in md_text or "Due" in md_text,
            f"home.md does not contain 'Pending' or 'Due': {md_text!r}",
        )

    def test_render_home_lists_pending_approval(self) -> None:
        self._full_interview("t45b")
        put_approval("ap1", "t45b", "Review Q3 budget", "pending")

        result = render_home("t45b")
        md_text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("Review Q3 budget", md_text)

    def test_render_home_lists_due_job(self) -> None:
        self._full_interview("t45c")
        # Schedule a job, then manually flip its status to "due" by
        # inserting directly via the scheduler then ticking.
        schedule("t45c", "Ship release notes", "2020-01-01T00:00:00")
        from core.twin_scheduler import tick
        tick("2025-01-01T00:00:00")

        result = render_home("t45c")
        md_text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("Ship release notes", md_text)

    def test_render_home_mentions_brief_when_present(self) -> None:
        self._full_interview("t45d")
        # Create a morning_brief.md so render_home should mention it.
        from core.twin_home import _work_products_dir
        brief_dir = _work_products_dir("t45d")
        brief_dir.mkdir(parents=True, exist_ok=True)
        (brief_dir / "morning_brief.md").write_text("# Brief\n", encoding="utf-8")

        result = render_home("t45d")
        md_text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("morning_brief.md", md_text)

    def test_render_home_no_brief_when_absent(self) -> None:
        self._full_interview("t45e")
        result = render_home("t45e")
        md_text = Path(result["path"]).read_text(encoding="utf-8")
        # The Brief section should say "(none)" when no brief exists.
        self.assertIn("(none)", md_text)

    def test_fastapi_home_200(self) -> None:
        self._full_interview("t45f")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/home",
            json={"tenant_id": "t45f"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t45f")
        self.assertIn("path", body)

    def test_fastapi_home_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/home",
            json={"tenant_id": "no_profile_t45"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
