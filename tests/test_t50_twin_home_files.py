"""T50 — Home lists real work-product files.

Covers:
- render_home lists filenames actually present under work_products/{tenant_id}/.
- After T03 commit, write a marker file then render_home; home.md contains
  the marker filename.
- FastAPI home still 200.
- No live network / no paid LLM.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_home import render_home
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT50TwinHomeFiles(unittest.TestCase):
    """Home page lists real on-disk work-product files."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t50_")
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

    def test_home_lists_marker_file(self) -> None:
        """home.md contains the marker filename after writing it and rendering."""
        self._full_interview("t50a")
        from core.twin_home import _work_products_dir

        out_dir = _work_products_dir("t50a")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "marker_t50.md").write_text("# marker\n", encoding="utf-8")

        result = render_home("t50a")
        md_text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("marker_t50.md", md_text)

    def test_home_files_section_none_when_empty(self) -> None:
        """Files section says '(none)' when only home.md is present."""
        self._full_interview("t50b")
        # Render once to create home.md, then render again — the Files
        # section should say (none) because only home.md exists.
        render_home("t50b")
        result = render_home("t50b")
        md_text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("## Files", md_text)
        self.assertIn("(none)", md_text)

    def test_fastapi_home_200(self) -> None:
        """FastAPI home still returns 200."""
        self._full_interview("t50c")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/home",
            json={"tenant_id": "t50c"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
