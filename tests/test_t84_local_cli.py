"""T84 — Local CLI prints home, queue, and provider status.

Covers:
- ``main(argv)`` prints HOME markdown, QUEUE (pending vs
  approved_waiting counts), and PROVIDER (kind + offline).
- ``main`` returns ``0``.
- ``core.twin_local`` does not import ``urllib``, ``requests``,
  ``socket``, or ``http.client``.
- AEGIS_DATA_DIR temp isolation; no live network.
"""

from __future__ import annotations

import ast
import contextlib
import inspect
import io
import os
import tempfile
import unittest
from uuid import uuid4

from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_local import main


class TestT84LocalCli(unittest.TestCase):
    """Local CLI prints home, queue, and provider status."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t84_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

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

    def test_main_prints_home_and_queue(self) -> None:
        """main() prints HOME markdown and QUEUE counts, returns 0."""
        tenant = f"t84-{uuid4().hex[:8]}"
        self._full_interview(tenant)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([tenant])

        out = buf.getvalue()
        self.assertEqual(rc, 0)
        # HOME section
        self.assertIn("## HOME", out)
        # QUEUE section with counts
        self.assertIn("## QUEUE", out)
        self.assertIn("pending:", out)
        self.assertIn("approved_waiting:", out)
        # Fresh tenant → zero pending / zero approved
        self.assertIn("pending: 0", out)
        self.assertIn("approved_waiting: 0", out)

    def test_main_prints_provider_kind(self) -> None:
        """main() prints PROVIDER section with kind value."""
        tenant = f"t84p-{uuid4().hex[:8]}"
        self._full_interview(tenant)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([tenant])

        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("## PROVIDER", out)
        # Default env → echo provider
        self.assertIn("kind: echo", out)
        self.assertIn("offline: False", out)

    def test_module_has_no_http_imports(self) -> None:
        """core.twin_local must not import urllib/requests/socket/http."""
        import core.twin_local as mod

        tree = ast.parse(inspect.getsource(mod))
        banned = {"urllib", "requests", "socket", "http.client"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in banned:
                        self.fail(
                            f"core.twin_local imports '{alias.name}'",
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in banned or mod.startswith("urllib."):
                    self.fail(
                        f"core.twin_local imports from '{mod}'",
                    )


if __name__ == "__main__":
    unittest.main()
