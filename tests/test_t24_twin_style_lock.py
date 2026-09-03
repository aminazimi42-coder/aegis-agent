"""T24 — Lock writing style from local text samples.

Covers:
- lock_style() without a consented profile raises ValueError.
- After a T03 commit, writing a sample containing
  "clarity clarity clarity shipping": style_lock.md contains clarity.
- FastAPI 200 on POST /api/v1/twin/style/lock.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_style_lock import lock_style
from fastapi.testclient import TestClient


class TestT24TwinStyleLock(unittest.TestCase):
    """Style-lock invariants."""

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

    def test_lock_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            lock_style("no_profile_t24", "/tmp")

    def test_lock_with_nonexistent_dir_raises_value_error(self) -> None:
        self._full_interview("t24b")
        with self.assertRaises(ValueError):
            lock_style("t24b", "/nonexistent/dir/does/not/exist")

    def test_lock_writes_style_lock_md_with_clarity(self) -> None:
        self._full_interview("t24a")

        # Create a samples directory with a .txt file.
        samples = Path(self._tmp) / "samples"
        samples.mkdir()
        (samples / "sample.txt").write_text(
            "clarity clarity clarity shipping\n",
            encoding="utf-8",
        )

        result = lock_style("t24a", str(samples))

        # Result shape.
        self.assertEqual(result["tenant_id"], "t24a")
        self.assertEqual(result["sample_count"], 1)
        self.assertIn("clarity", result["top_words"])

        # style_lock.md exists and contains clarity.
        lock_path = Path(self._tmp) / "work_products" / "t24a" / "style_lock.md"
        self.assertTrue(lock_path.exists())
        text = lock_path.read_text(encoding="utf-8")
        self.assertIn("clarity", text)

    def test_lock_overwrites_on_second_call(self) -> None:
        self._full_interview("t24c")
        samples = Path(self._tmp) / "samples"
        samples.mkdir()
        (samples / "sample.txt").write_text(
            "clarity clarity clarity shipping\n",
            encoding="utf-8",
        )

        result1 = lock_style("t24c", str(samples))
        lock_path = Path(result1["path"])
        text1 = lock_path.read_text(encoding="utf-8")

        # Overwrite with different content.
        (samples / "sample.txt").write_text(
            "deploy deploy deploy production\n",
            encoding="utf-8",
        )
        result2 = lock_style("t24c", str(samples))
        text2 = lock_path.read_text(encoding="utf-8")

        self.assertEqual(result1["path"], result2["path"])
        self.assertIn("clarity", text1)
        self.assertIn("deploy", text2)

    def test_lock_reads_md_and_txt_files(self) -> None:
        self._full_interview("t24d")
        samples = Path(self._tmp) / "samples"
        samples.mkdir()
        (samples / "notes.md").write_text(
            "# Shipping\n\nshipping shipping release\n",
            encoding="utf-8",
        )
        (samples / "draft.txt").write_text(
            "clarity clarity clarity focus\n",
            encoding="utf-8",
        )

        result = lock_style("t24d", str(samples))
        self.assertEqual(result["sample_count"], 2)
        self.assertIn("clarity", result["top_words"])
        self.assertIn("shipping", result["top_words"])

    def test_lock_drops_short_words(self) -> None:
        self._full_interview("t24e")
        samples = Path(self._tmp) / "samples"
        samples.mkdir()
        (samples / "sample.txt").write_text(
            "the and for but clarity clarity clarity\n",
            encoding="utf-8",
        )

        result = lock_style("t24e", str(samples))
        self.assertIn("clarity", result["top_words"])
        # Short words (the, and, for, but) should not appear.
        for short in ("the", "and", "for", "but"):
            self.assertNotIn(short, result["top_words"])

    def test_fastapi_post_200(self) -> None:
        self._full_interview("t24f")
        samples = Path(self._tmp) / "samples"
        samples.mkdir()
        (samples / "sample.txt").write_text(
            "clarity clarity clarity shipping\n",
            encoding="utf-8",
        )

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/style/lock",
            json={"tenant_id": "t24f", "samples_dir": str(samples)},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t24f")
        self.assertIn("clarity", body["top_words"])

    def test_fastapi_post_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/style/lock",
            json={"tenant_id": "no_profile_t24", "samples_dir": "/tmp"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
