"""T13 — Local twin CLI operator.

Covers:
- ``status`` exits 0 and stdout contains ``1.0.0-rc1``.
- Full interview flow: ``interview-start`` + 6 answers + ``interview-commit``
  with consent true exits 0.
- ``actions-execute`` before ``actions-approve`` exits 2.
- Full lifecycle: ``actions-propose`` → ``actions-approve`` →
  ``actions-execute`` → ``render`` exits 0; ``weekly_plan.md`` exists
  under ``AEGIS_DATA_DIR``.
- No live network.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_PY = sys.executable
_CLI = str(Path(__file__).resolve().parent.parent / "tools" / "twin_cli.py")


def _run_cli(*args: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    """Run the CLI with the given args; return (exit_code, stdout)."""
    cmd = [_PY, _CLI, *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(_CLI).resolve().parent.parent),
    )
    return result.returncode, result.stdout.strip()


class TestT13TwinCli(unittest.TestCase):
    """Local twin CLI invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        self._env = {**os.environ, "AEGIS_DATA_DIR": self._tmp}

    def tearDown(self) -> None:
        pass

    # ------------------------------------------------------------------ #
    # status
    # ------------------------------------------------------------------ #

    def test_status_exit_0_and_contains_version(self) -> None:
        code, stdout = _run_cli("status", env=self._env)
        self.assertEqual(code, 0, f"exit {code}; stdout: {stdout}")
        self.assertIn("1.0.0-rc1", stdout)

    # ------------------------------------------------------------------ #
    # full interview flow
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete interview via the CLI; return the session id."""
        from core.twin_interview import QUESTIONS

        code, stdout = _run_cli("interview-start", "--tenant", tenant_id, env=self._env)
        self.assertEqual(code, 0, f"interview-start exit {code}: {stdout}")

        import json

        session = json.loads(stdout)
        sid = session["session_id"]

        for q in QUESTIONS:
            code, stdout = _run_cli(
                "interview-answer",
                "--session",
                sid,
                "--question",
                q["id"],
                "--text",
                f"ans-{q['id']}",
                env=self._env,
            )
            self.assertEqual(code, 0, f"answer {q['id']} exit {code}: {stdout}")

        code, stdout = _run_cli(
            "interview-commit",
            "--session",
            sid,
            "--consent",
            "true",
            env=self._env,
        )
        self.assertEqual(code, 0, f"interview-commit exit {code}: {stdout}")

        return sid

    def test_full_interview_flow_exit_0(self) -> None:
        """interview-start + 6 answers + commit consent true → exit 0."""
        sid = self._full_interview("t13a")
        self.assertTrue(sid.startswith("twin-"))

    # ------------------------------------------------------------------ #
    # execute before approve → exit 2
    # ------------------------------------------------------------------ #

    def test_execute_before_approve_exit_2(self) -> None:
        """actions-execute on a proposed (not approved) action exits 2."""
        self._full_interview("t13b")

        code, stdout = _run_cli("actions-propose", "--tenant", "t13b", env=self._env)
        self.assertEqual(code, 0, f"propose exit {code}: {stdout}")

        import json

        actions = json.loads(stdout)["actions"]
        self.assertGreaterEqual(len(actions), 1)

        first_action_id = actions[0]["action_id"]
        code, stdout = _run_cli(
            "actions-execute",
            "--action-id",
            first_action_id,
            "--tenant",
            "t13b",
            env=self._env,
        )
        self.assertEqual(code, 2, f"execute should fail exit 2, got {code}: {stdout}")
        self.assertIn("error", json.loads(stdout))

    # ------------------------------------------------------------------ #
    # propose → approve → execute → render → exit 0
    # ------------------------------------------------------------------ #

    def test_full_lifecycle_and_render(self) -> None:
        """propose → approve → execute → render exits 0 with weekly_plan.md."""
        self._full_interview("t13c")

        # Propose
        code, stdout = _run_cli("actions-propose", "--tenant", "t13c", env=self._env)
        self.assertEqual(code, 0, f"propose exit {code}: {stdout}")

        import json

        actions = json.loads(stdout)["actions"]
        self.assertGreaterEqual(len(actions), 1)

        # Approve the first action
        first_action_id = actions[0]["action_id"]
        # Compute the current digest to pass as expected_payload_sha256.
        from core.twin_actions import _action_digest, _load_action

        _a = _load_action(first_action_id)
        assert _a is not None
        digest = _action_digest(_a)
        code, stdout = _run_cli(
            "actions-approve",
            "--action-id",
            first_action_id,
            "--tenant",
            "t13c",
            "--actor",
            "tester",
            "--expected-payload-sha256",
            digest,
            env=self._env,
        )
        self.assertEqual(code, 0, f"approve exit {code}: {stdout}")
        approved = json.loads(stdout)
        self.assertEqual(approved["status"], "approved")

        # Execute
        code, stdout = _run_cli(
            "actions-execute",
            "--action-id",
            first_action_id,
            "--tenant",
            "t13c",
            env=self._env,
        )
        self.assertEqual(code, 0, f"execute exit {code}: {stdout}")
        executed = json.loads(stdout)
        self.assertEqual(executed["status"], "executed")

        # Render
        code, stdout = _run_cli("render", "--tenant", "t13c", env=self._env)
        self.assertEqual(code, 0, f"render exit {code}: {stdout}")
        rendered = json.loads(stdout)
        self.assertEqual(rendered["tenant_id"], "t13c")
        self.assertEqual(len(rendered["files"]), 2)

        # weekly_plan.md exists under AEGIS_DATA_DIR
        for fpath in rendered["files"]:
            self.assertTrue(
                Path(fpath).exists(),
                f"missing file: {fpath}",
            )
            # File must be under the temp data dir.
            self.assertTrue(
                str(Path(fpath)).startswith(self._tmp),
                f"file not under AEGIS_DATA_DIR: {fpath}",
            )

        # Specifically weekly_plan.md must exist.
        plan_path = Path(rendered["files"][0])
        self.assertIn("weekly_plan.md", str(plan_path))
        self.assertTrue(plan_path.exists())


if __name__ == "__main__":
    unittest.main()
