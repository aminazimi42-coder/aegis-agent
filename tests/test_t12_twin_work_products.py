"""T12 — Local work-product files from the twin.

Covers:
- render without a consented profile raises ValueError.
- After a T03-style commit + one git ingest_event for repo acme/core:
  render creates both md files; weekly_plan.md contains acme/core; files len == 2.
- FastAPI client 200 on POST /api/v1/twin/work-products/render.
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
from core.twin_work_products import render
from fastapi.testclient import TestClient


class TestT12TwinWorkProducts(unittest.TestCase):
    """Local work-product rendering invariants."""

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
            render("no_profile_t12")

    def test_render_creates_both_md_files_with_acme_core(self) -> None:
        self._full_interview("t12a")
        ingest_event(
            "t12a",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "aaa", "subject": "feat: init"},
        )

        result = render("t12a")

        # Result shape.
        self.assertEqual(result["tenant_id"], "t12a")
        self.assertEqual(len(result["files"]), 2)

        # Both files exist on disk.
        for fpath in result["files"]:
            self.assertTrue(Path(fpath).exists(), f"missing file: {fpath}")

        # weekly_plan.md contains acme/core.
        plan_path = result["files"][0]
        plan_text = Path(plan_path).read_text(encoding="utf-8")
        self.assertIn("acme/core", plan_text)

        # review_notes.md has a section for acme/core.
        review_path = result["files"][1]
        review_text = Path(review_path).read_text(encoding="utf-8")
        self.assertIn("acme/core", review_text)

    def test_render_overwrites_on_second_call(self) -> None:
        self._full_interview("t12b")
        ingest_event(
            "t12b",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "bbb", "subject": "fix: bug"},
        )
        result1 = render("t12b")
        plan1 = Path(result1["files"][0]).read_text(encoding="utf-8")

        # Second render should overwrite (same content since no new events).
        result2 = render("t12b")
        plan2 = Path(result2["files"][0]).read_text(encoding="utf-8")

        self.assertEqual(result1["files"], result2["files"])
        self.assertEqual(plan1, plan2)

    def test_fastapi_render_200(self) -> None:
        self._full_interview("t12c")
        ingest_event(
            "t12c",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "ccc", "subject": "feat: init"},
        )

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/work-products/render",
            json={"tenant_id": "t12c"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t12c")
        self.assertEqual(len(body["files"]), 2)

    def test_fastapi_render_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/work-products/render",
            json={"tenant_id": "no_profile_t12"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
