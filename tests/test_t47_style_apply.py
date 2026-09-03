"""T47 — apply_style from style_lock.md into brief and home renders.

Covers:
- apply_style without a lock file returns the input unchanged.
- After T03 commit and lock_style on a temp dir with one .txt containing
  "clarity precision cadence extra", render_brief and render_home output
  files contain "Voice:".
- No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_home import render_home
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_morning_brief import render_brief
from core.twin_style_lock import apply_style, lock_style


class TestT47StyleApply(unittest.TestCase):
    """Style-apply invariants."""

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

    def test_apply_style_without_lock_returns_input(self) -> None:
        """apply_style returns the input when no style_lock.md exists."""
        result = apply_style("no_lock_t47", "hello world")
        self.assertEqual(result, "hello world")

    def test_apply_style_with_lock_prepends_voice(self) -> None:
        """apply_style prepends 'Voice:' + up to three top words."""
        self._full_interview("t47a")
        samples = Path(self._tmp) / "samples"
        samples.mkdir()
        (samples / "sample.txt").write_text(
            "clarity precision cadence extra\n",
            encoding="utf-8",
        )
        lock_style("t47a", str(samples))
        result = apply_style("t47a", "body text")
        self.assertTrue(result.startswith("Voice:"))
        self.assertIn("body text", result)

    def test_brief_contains_voice_after_lock(self) -> None:
        """render_brief file contains 'Voice:' after lock_style."""
        self._full_interview("t47b")
        samples = Path(self._tmp) / "samples"
        samples.mkdir()
        (samples / "sample.txt").write_text(
            "clarity precision cadence extra\n",
            encoding="utf-8",
        )
        lock_style("t47b", str(samples))
        result = render_brief("t47b")
        path = Path(result["path"])
        text = path.read_text(encoding="utf-8")
        self.assertIn("Voice:", text)

    def test_home_contains_voice_after_lock(self) -> None:
        """render_home file contains 'Voice:' after lock_style."""
        self._full_interview("t47c")
        samples = Path(self._tmp) / "samples"
        samples.mkdir()
        (samples / "sample.txt").write_text(
            "clarity precision cadence extra\n",
            encoding="utf-8",
        )
        lock_style("t47c", str(samples))
        result = render_home("t47c")
        path = Path(result["path"])
        text = path.read_text(encoding="utf-8")
        self.assertIn("Voice:", text)


if __name__ == "__main__":
    unittest.main()
