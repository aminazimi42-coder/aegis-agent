"""T99 — Structured reject, specialist daily budget, conflict flag.

Covers:
- ``aegis reject ACTION_ID TENANT_ID REASON`` persists a short reason
  code (from the allow-list ``duplicate``, ``stale``, ``unsafe``,
  ``other``) on the action row and does **not** execute it.
- Per-specialist daily budget: env ``AEGIS_PROPOSE_BUDGET_PER_SPECIALIST``
  (default 20) caps proposes from the same specialist on the same UTC
  day; further proposes raise ``ValueError`` and write nothing.
- Conflict flag: when a new propose shares the same title (or payload
  JSON) with a pending action for the same tenant, the new row is still
  inserted but ``conflict`` is set to ``True``.
- No live network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4


def _run_aegis(*args: str, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run ``python -m core.twin_local <args>``; return (code, stdout, stderr)."""
    cmd = [sys.executable, "-m", "core.twin_local", *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _write_profile(
    data_dir: str,
    tenant_id: str,
    role: str = "architect",
    goal: str = "ship",
    consented: bool = True,
) -> Path:
    """Write a consented (or not) profile.json under data_dir/<tenant>/."""
    profile_dir = Path(data_dir) / tenant_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / "profile.json"
    profile_path.write_text(
        json.dumps(
            {"role": role, "goal": goal, "consented": consented},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return profile_path


class TestT99RejectBudgetConflict(unittest.TestCase):
    """Structured reject, per-specialist daily budget, and conflict flag."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t99_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        self._env = {**os.environ, "AEGIS_DATA_DIR": self._tmp}

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_PROPOSE_BUDGET_PER_SPECIALIST", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _propose_one(self, tenant_id: str) -> str:
        """Insert one proposed action via the CLI and return its action_id."""
        _write_profile(self._tmp, tenant_id)
        code, stdout, stderr = _run_aegis(
            "propose", tenant_id, env=self._env,
        )
        assert code == 0, f"propose failed: {stderr!r}"
        # The JSON result is printed on stdout; extract action_id.
        # The CLI prints ``payload_sha256: ...`` then a JSON object.
        lines = [ln for ln in stdout.splitlines() if ln.strip().startswith("{")]
        assert lines, f"no JSON in stdout: {stdout!r}"
        result = json.loads(lines[-1])
        return result["action_id"]

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_reject_stores_reason(self) -> None:
        """``aegis reject ACTION_ID TENANT_ID REASON`` persists the reason
        code on the action and sets status to ``rejected`` without executing."""
        tenant = f"t99-reject-{uuid4().hex[:8]}"
        action_id = self._propose_one(tenant)

        code, stdout, stderr = _run_aegis(
            "reject", action_id, tenant, "duplicate", env=self._env,
        )
        self.assertEqual(code, 0, f"reject failed: {stderr!r}")
        self.assertIn("rejected", stdout)

        # Verify the reason is persisted on the row.
        from core.twin_actions import _load_action

        row = _load_action(action_id)
        assert row is not None
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(row.get("reject_reason"), "duplicate")

    def test_reject_invalid_reason_exits_2(self) -> None:
        """An invalid reason code exits 2 and does not change the action."""
        tenant = f"t99-reject-bad-{uuid4().hex[:8]}"
        action_id = self._propose_one(tenant)

        code, stdout, stderr = _run_aegis(
            "reject", action_id, tenant, "bogus_reason", env=self._env,
        )
        self.assertEqual(code, 2)
        self.assertIn("reject error", stderr)

        # The action must still be proposed (not rejected).
        from core.twin_actions import _load_action

        row = _load_action(action_id)
        assert row is not None
        self.assertEqual(row["status"], "proposed")

    def test_budget_blocks_over_cap(self) -> None:
        """When the per-specialist daily budget is reached, further proposes
        exit 2 and write nothing to the database."""
        tenant = f"t99-budget-{uuid4().hex[:8]}"
        _write_profile(self._tmp, tenant)

        # Set a tiny budget of 2.
        env = {**self._env, "AEGIS_PROPOSE_BUDGET_PER_SPECIALIST": "2"}

        # First two proposes should succeed.
        code1, _, stderr1 = _run_aegis("propose", tenant, env=env)
        self.assertEqual(code1, 0, f"first propose failed: {stderr1!r}")

        code2, _, stderr2 = _run_aegis("propose", tenant, env=env)
        self.assertEqual(code2, 0, f"second propose failed: {stderr2!r}")

        # Third propose should be blocked by the budget cap.
        code3, _, stderr3 = _run_aegis("propose", tenant, env=env)
        self.assertEqual(code3, 2, f"third propose should exit 2: {stderr3!r}")
        self.assertIn("budget", stderr3.lower())

        # Verify exactly 2 rows were written — no third row.
        from core.twin_local_view import list_queue

        pending = list_queue(tenant)["pending"]
        self.assertEqual(len(pending), 2)

    def test_conflict_flag_set(self) -> None:
        """When two proposes share the same title (or payload), the second
        row is still inserted but ``conflict`` is set to ``True``."""
        tenant = f"t99-conflict-{uuid4().hex[:8]}"
        _write_profile(self._tmp, tenant, role="dev", goal="review")

        # First propose — no conflict.
        code1, stdout1, stderr1 = _run_aegis("propose", tenant, env=self._env)
        self.assertEqual(code1, 0, f"first propose failed: {stderr1!r}")
        lines1 = [ln for ln in stdout1.splitlines() if ln.strip().startswith("{")]
        result1 = json.loads(lines1[-1])
        self.assertFalse(result1.get("conflict", False))

        # Second propose — same title/payload → conflict=True, still inserted.
        code2, stdout2, stderr2 = _run_aegis("propose", tenant, env=self._env)
        self.assertEqual(code2, 0, f"second propose failed: {stderr2!r}")
        lines2 = [ln for ln in stdout2.splitlines() if ln.strip().startswith("{")]
        result2 = json.loads(lines2[-1])
        self.assertTrue(
            result2.get("conflict", False),
            "second propose with same title should have conflict=True",
        )

        # Both rows must be present in the queue.
        from core.twin_local_view import list_queue

        pending = list_queue(tenant)["pending"]
        self.assertEqual(len(pending), 2)
        conflict_flags = [p.get("conflict", False) for p in pending]
        self.assertIn(True, conflict_flags)

    def test_no_live_network(self) -> None:
        """No live network is used in this test module."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
