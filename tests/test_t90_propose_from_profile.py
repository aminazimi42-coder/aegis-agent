"""T90 — ``aegis propose TENANT_ID`` inserts one proposed twin_action from profile.

Covers:
- Without a local ``profile.json`` the command exits ``2`` and writes nothing.
- With a consented ``profile.json`` (``consented=true``) the command inserts
  exactly one ``proposed`` action whose payload includes ``role`` and
  ``goal``; the pending queue length increases by exactly one.
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
    role: str,
    goal: str,
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


class TestT90ProposeFromProfile(unittest.TestCase):
    """``aegis propose TENANT_ID`` from the local consented profile."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        self._env = {**os.environ, "AEGIS_DATA_DIR": self._tmp}

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _queue_pending_count(self, tenant_id: str) -> int:
        from core.twin_local_view import list_queue

        return len(list_queue(tenant_id)["pending"])

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_propose_without_profile_exits_2(self) -> None:
        """Missing profile.json → exit 2, nothing inserted."""
        before = self._queue_pending_count("t90_no_profile")
        self.assertEqual(before, 0)

        code, stdout, stderr = _run_aegis("propose", "t90_no_profile", env=self._env)
        self.assertEqual(code, 2, f"exit {code}: stdout={stdout!r} stderr={stderr!r}")

        after = self._queue_pending_count("t90_no_profile")
        self.assertEqual(after, 0, "nothing should have been inserted")

    def test_propose_without_consent_exits_2(self) -> None:
        """profile.json present but consented=false → exit 2, nothing inserted."""
        _write_profile(
            self._tmp,
            "t90_no_consent",
            role="engineer",
            goal="ship",
            consented=False,
        )

        before = self._queue_pending_count("t90_no_consent")
        self.assertEqual(before, 0)

        code, stdout, stderr = _run_aegis(
            "propose", "t90_no_consent", env=self._env,
        )
        self.assertEqual(code, 2, f"exit {code}: stdout={stdout!r} stderr={stderr!r}")

        after = self._queue_pending_count("t90_no_consent")
        self.assertEqual(after, 0, "nothing should have been inserted")

    def test_propose_with_consent_increments_pending(self) -> None:
        """Consented profile → one proposed action inserted; pending +1."""
        _write_profile(
            self._tmp,
            "t90_ok",
            role="architect",
            goal="review the digest",
            consented=True,
        )

        before = self._queue_pending_count("t90_ok")
        self.assertEqual(before, 0)

        code, stdout, stderr = _run_aegis("propose", "t90_ok", env=self._env)
        self.assertEqual(code, 0, f"exit {code}: stdout={stdout!r} stderr={stderr!r}")

        after = self._queue_pending_count("t90_ok")
        self.assertEqual(after, 1, "exactly one proposed action should be pending")

        # The single pending action must carry role+goal in its payload.
        from core.twin_local_view import list_queue

        pending = list_queue("t90_ok")["pending"]
        self.assertEqual(len(pending), 1)
        action = pending[0]
        self.assertEqual(action["status"], "proposed")
        self.assertEqual(action["tenant_id"], "t90_ok")
        payload = action.get("payload")
        if isinstance(payload, str):
            payload = json.loads(payload)
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload.get("role"), "architect")
        self.assertEqual(payload.get("goal"), "review the digest")

        # Second propose → pending becomes 2 (idempotent inserts, one per call).
        code, stdout, stderr = _run_aegis("propose", "t90_ok", env=self._env)
        self.assertEqual(code, 0, f"exit {code}: stdout={stdout!r} stderr={stderr!r}")
        after2 = self._queue_pending_count("t90_ok")
        self.assertEqual(after2, 2, "second propose should add exactly one more")

    def test_propose_usage_error_exits_2(self) -> None:
        """Wrong number of args → exit 2, nothing inserted."""
        code, stdout, stderr = _run_aegis("propose", env=self._env)
        self.assertEqual(code, 2)

        code, stdout, stderr = _run_aegis("propose", "t90_extra", "extra", env=self._env)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
