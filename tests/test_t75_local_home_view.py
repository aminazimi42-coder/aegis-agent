"""T75 — Local home viewer without HTTP.

Covers:
- ``read_home(tenant_id)`` returns the markdown text of ``home.md``.
- If ``home.md`` is missing, ``render_home`` is called first then the
  file is read back.
- ``core.twin_local_view`` does not import ``urllib``, ``requests``,
  ``socket``, or ``http.client``.
- AEGIS_DATA_DIR temp isolation; no live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_local_view import read_home


class TestT75LocalHomeView(unittest.TestCase):
    """Read home.md from disk without calling HTTP."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t75_")
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

    def test_read_home_returns_markdown(self) -> None:
        """read_home returns the text written by render_home."""
        self._full_interview("t75a")
        md = read_home("t75a")
        self.assertIsInstance(md, str)
        self.assertGreater(len(md), 0)
        # The file on disk should match what read_home returned.
        on_disk = (
            Path(self._tmp) / "work_products" / "t75a" / "home.md"
        )
        self.assertTrue(on_disk.is_file(), "home.md was not written")
        self.assertEqual(md, on_disk.read_text(encoding="utf-8"))

    def test_read_home_renders_when_missing(self) -> None:
        """When home.md does not exist, read_home renders then reads."""
        self._full_interview("t75b")
        # No prior home.md — read_home must create it.
        home_path = (
            Path(self._tmp) / "work_products" / "t75b" / "home.md"
        )
        self.assertFalse(home_path.is_file(), "home.md pre-existed")
        md = read_home("t75b")
        self.assertGreater(len(md), 0)
        self.assertTrue(home_path.is_file(), "read_home did not render home.md")

    def test_module_has_no_http_imports(self) -> None:
        """core.twin_local_view must not import urllib/requests/socket/http."""
        import ast
        import inspect

        from core import twin_local_view

        tree = ast.parse(inspect.getsource(twin_local_view))
        forbidden = {"urllib", "requests", "socket", "http.client"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    self.assertNotIn(
                        top,
                        forbidden,
                        f"core.twin_local_view imports '{alias.name}'",
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "")
                top = mod.split(".")[0]
                self.assertNotIn(
                    top,
                    forbidden,
                    f"core.twin_local_view imports from '{mod}'",
                )


if __name__ == "__main__":
    unittest.main()
