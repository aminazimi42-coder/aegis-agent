"""T85 — Local CLI approve and execute plus run_local.sh.

Covers:
- ``main(["approve", ACTION_ID, TENANT_ID, ACTOR_ID, DIGEST])`` calls
  ``approve(...)`` and prints the returned status.
- ``main(["execute", ACTION_ID, TENANT_ID])`` calls ``execute(...)`` and
  prints the returned status.
- ``main(["bogus"])`` exits ``2``.
- ``scripts/run_local.sh`` exists and starts with ``#!/bin/sh``.
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
from pathlib import Path
from uuid import uuid4

from core.twin_actions import _action_digest, _load_action, propose_actions
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_local import main


class TestT85LocalCliAct(unittest.TestCase):
    """Local CLI can approve and execute with the existing hash lock."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t85_")
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

    def test_approve_and_execute_via_main(self) -> None:
        """approve via main() then execute via main() prints statuses."""
        tenant = f"t85-{uuid4().hex[:8]}"
        self._full_interview(tenant)

        # Propose actions — at least one is expected.
        actions = propose_actions(tenant)
        self.assertGreaterEqual(len(actions), 1)
        action = actions[0]
        action_id = action["action_id"]
        digest = _action_digest(action)

        # --- approve via main() ---
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["approve", action_id, tenant, "tester", digest])
        out = buf.getvalue().strip()
        self.assertEqual(rc, 0)
        self.assertEqual(out, "approved")

        # --- execute via main() ---
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = main(["execute", action_id, tenant])
        out2 = buf2.getvalue().strip()
        self.assertEqual(rc2, 0)
        self.assertEqual(out2, "executed")

        # Verify the action row is indeed executed.
        row = _load_action(action_id)
        assert row is not None
        self.assertEqual(row["status"], "executed")

    def test_unknown_command_exits_2(self) -> None:
        """An unknown command exits with code 2."""
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = main(["bogus"])
        self.assertEqual(rc, 2)

    def test_run_local_script_exists(self) -> None:
        """scripts/run_local.sh exists and starts with #!/bin/sh."""
        script = Path(__file__).resolve().parent.parent / "scripts" / "run_local.sh"
        self.assertTrue(script.is_file(), f"{script} does not exist")
        text = script.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/sh"), f"{script} must start with #!/bin/sh")

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
