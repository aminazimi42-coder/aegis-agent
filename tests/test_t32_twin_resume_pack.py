"""T32 — Principal one-pager / resume pack.

Covers:
- render_resume() without a consented profile raises ValueError.
- After a T03 commit: resume.md exists and contains the tenant id or a
  profile name token.
- FastAPI 200 on POST /api/v1/twin/resume/render.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_resume_pack import render_resume
from fastapi.testclient import TestClient


class TestT32TwinResumePack(unittest.TestCase):
    """Resume-pack invariants."""

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

    def test_render_resume_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            render_resume("no_profile_t32")

    def test_render_resume_contains_tenant_id_or_profile_name(self) -> None:
        self._full_interview("t32a")

        result = render_resume("t32a")

        self.assertEqual(result["tenant_id"], "t32a")
        resume_path = Path(result["path"])
        self.assertTrue(resume_path.exists())

        text = resume_path.read_text(encoding="utf-8")
        # The resume must contain the tenant id or a profile name token.
        self.assertIn("t32a", text)
        # Must include the Work Products section header.
        self.assertIn("## Work Products", text)
        # Must end with the approval gate line.
        self.assertIn(
            "Do not act on this resume without written principal approval.",
            text,
        )

    def test_render_resume_lists_existing_work_product_files(self) -> None:
        self._full_interview("t32b")

        # Create a work-product file first (e.g. from a prior render call).
        render_resume("t32b")  # creates resume.md
        # Call again — resume.md should now appear in the work products list.
        result = render_resume("t32b")
        text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("resume.md", text)

    def test_render_resume_overwrites_on_second_call(self) -> None:
        self._full_interview("t32c")

        render_resume("t32c")
        path = Path(self._tmp) / "work_products" / "t32c" / "resume.md"
        text1 = path.read_text(encoding="utf-8")
        self.assertIn("t32c", text1)

        render_resume("t32c")
        text2 = path.read_text(encoding="utf-8")
        self.assertIn("t32c", text2)

    def test_fastapi_resume_render_200(self) -> None:
        self._full_interview("t32d")

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/resume/render",
            json={"tenant_id": "t32d"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t32d")
        self.assertTrue(Path(body["path"]).exists())

    def test_fastapi_resume_render_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/resume/render",
            json={"tenant_id": "no_profile_t32"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
