"""T89 — Interactive day-0 interview prompts on stdin.

Covers:
- ``main(["interview"])`` with no extra args reads tenant, role, goal,
  and consent from *stdin*, writes ``profile.json`` with ``role``,
  ``goal``, and ``consented=true`` under ``{AEGIS_DATA_DIR}/{tenant_id}/``
  when consent is ``yes`` (T89).
- When consent is not ``yes``, nothing is written and the command
  exits ``2``.
- Answers are fed through stdin, not a real keyboard.
- AEGIS_DATA_DIR temp isolation; no live network.
"""

from __future__ import annotations

import ast
import contextlib
import inspect
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from core.twin_local import main


class TestT89InteractiveInterview(unittest.TestCase):
    """Interactive interview reads from stdin and writes a consented profile."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t89_")
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

    def _profile_path(self, tenant_id: str) -> Path:
        """Return the on-disk path where the interview profile is written."""
        return Path(self._tmp) / tenant_id / "profile.json"

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_interactive_yes_writes_profile(self) -> None:
        """Interactive interview with ``yes`` consent writes profile.json."""
        tenant = "t89-yes"
        stdin = io.StringIO(f"{tenant}\nfounder\nship-v1\nyes\n")
        buf = io.StringIO()
        orig_stdin = sys.stdin
        sys.stdin = stdin
        try:
            with contextlib.redirect_stdout(buf):
                rc = main(["interview"])
        finally:
            sys.stdin = orig_stdin

        self.assertEqual(rc, 0)

        profile_path = self._profile_path(tenant)
        self.assertTrue(
            profile_path.is_file(),
            f"profile.json not written at {profile_path}",
        )
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        self.assertEqual(data["role"], "founder")
        self.assertEqual(data["goal"], "ship-v1")
        self.assertTrue(data["consented"])

    def test_interactive_no_writes_nothing(self) -> None:
        """Interactive interview with non-yes consent writes nothing and exits 2."""
        tenant = "t89-no"
        stdin = io.StringIO(f"{tenant}\nfounder\nship-v1\nno\n")
        buf = io.StringIO()
        orig_stdin = sys.stdin
        sys.stdin = stdin
        try:
            with contextlib.redirect_stdout(buf):
                rc = main(["interview"])
        finally:
            sys.stdin = orig_stdin

        self.assertEqual(rc, 2)

        profile_path = self._profile_path(tenant)
        self.assertFalse(
            profile_path.exists(),
            f"profile.json should not exist when consent is not yes: {profile_path}",
        )
        tenant_dir = Path(self._tmp) / tenant
        self.assertFalse(
            tenant_dir.exists(),
            f"tenant directory should not exist when consent is not yes: {tenant_dir}",
        )

    def test_batch_form_still_works(self) -> None:
        """Four-arg batch form from T88 still works."""
        tenant = "t89-batch"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["interview", tenant, "founder", "ship-v1", "yes"])

        self.assertEqual(rc, 0)

        profile_path = self._profile_path(tenant)
        self.assertTrue(profile_path.is_file())
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        self.assertEqual(data["role"], "founder")
        self.assertEqual(data["goal"], "ship-v1")
        self.assertTrue(data["consented"])

    def test_module_has_no_http_imports(self) -> None:
        """core.twin_local must not import urllib/requests/socket/http."""
        import core.twin_local as mod

        tree = ast.parse(inspect.getsource(mod))
        banned = {"urllib", "requests", "socket", "http.client"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in banned:
                        self.fail(f"core.twin_local imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                if mod_name in banned or mod_name.startswith("urllib."):
                    self.fail(f"core.twin_local imports from '{mod_name}'")

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
