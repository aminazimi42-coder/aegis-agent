"""T25 — Local PR review notes from a diff file.

Covers:
- review_diff() without a consented profile raises ValueError.
- After a T03 commit, writing a tiny diff containing
  "+++ b/acme/core.py": pr_review.md contains acme/core.py
  and "Do not push".
- FastAPI 200 on POST /api/v1/twin/pr/review.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_pr_review import review_diff
from fastapi.testclient import TestClient


class TestT25TwinPrReview(unittest.TestCase):
    """PR-review invariants."""

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

    def _write_diff(self, content: str) -> str:
        """Write a diff file to the temp dir and return its path."""
        diff_path = Path(self._tmp) / "changes.diff"
        diff_path.write_text(content, encoding="utf-8")
        return str(diff_path)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_review_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            review_diff("no_profile_t25", "/tmp/nonexistent.diff")

    def test_review_with_nonexistent_diff_raises_value_error(self) -> None:
        self._full_interview("t25b")
        with self.assertRaises(ValueError):
            review_diff("t25b", str(Path(self._tmp) / "no_such_file.diff"))

    def test_review_writes_pr_review_md_with_file_and_safety(self) -> None:
        self._full_interview("t25a")
        diff_path = self._write_diff(
            "diff --git a/acme/core.py b/acme/core.py\n"
            "--- a/acme/core.py\n"
            "+++ b/acme/core.py\n"
            "@@ -1,3 +1,3 @@\n"
            "-old line\n"
            "+new line\n"
        )

        result = review_diff("t25a", diff_path)

        self.assertEqual(result["tenant_id"], "t25a")
        self.assertEqual(result["path"], diff_path)
        self.assertIn("acme/core.py", result["files"])

        review_path = (
            Path(self._tmp) / "work_products" / "t25a" / "pr_review.md"
        )
        self.assertTrue(review_path.exists())
        text = review_path.read_text(encoding="utf-8")
        self.assertIn("acme/core.py", text)
        self.assertIn("Do not push to origin", text)

    def test_review_overwrites_on_second_call(self) -> None:
        self._full_interview("t25c")
        diff1 = self._write_diff(
            "+++ b/acme/first.py\n"
            "+change\n"
        )
        result1 = review_diff("t25c", diff1)
        review_path = Path(result1.get("path", ""))
        # The returned "path" is the diff path, not the output file;
        # locate the output file directly.
        review_path = (
            Path(self._tmp) / "work_products" / "t25c" / "pr_review.md"
        )
        text1 = review_path.read_text(encoding="utf-8")
        self.assertIn("acme/first.py", text1)

        # Overwrite the diff file in place so path stays the same.
        Path(diff1).write_text(
            "+++ b/acme/second.py\n"
            "+change\n",
            encoding="utf-8",
        )
        review_diff("t25c", diff1)
        text2 = review_path.read_text(encoding="utf-8")
        self.assertIn("acme/second.py", text2)

    def test_review_parses_diff_git_lines(self) -> None:
        self._full_interview("t25d")
        diff_path = self._write_diff(
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "diff --git a/src/util.py b/src/util.py\n"
            "--- a/src/util.py\n"
            "+++ b/src/util.py\n"
        )
        result = review_diff("t25d", diff_path)
        self.assertIn("src/app.py", result["files"])
        self.assertIn("src/util.py", result["files"])

    def test_fastapi_post_200(self) -> None:
        self._full_interview("t25e")
        diff_path = self._write_diff(
            "+++ b/acme/core.py\n"
            "+new\n"
        )

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/pr/review",
            json={"tenant_id": "t25e", "diff_path": diff_path},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t25e")
        self.assertIn("acme/core.py", body["files"])

    def test_fastapi_post_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/pr/review",
            json={
                "tenant_id": "no_profile_t25",
                "diff_path": "/tmp/nonexistent.diff",
            },
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
