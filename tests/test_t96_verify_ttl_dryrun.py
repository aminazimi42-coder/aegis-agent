"""T96 — verify digests, expire stale approve, dry-run execute.

Verifies:

* ``verify TENANT_ID`` recomputes payload digests for pending actions,
  prints mismatch lines, and exits ``1`` on mismatch / ``0`` when clean.
* An approve older than ``AEGIS_APPROVE_TTL_HOURS`` (default 24) cannot be
  executed — the receipt is not written and status stays ``approved``.
  The digest lock stays in force regardless of age.
* ``execute --dry-run ACTION_ID TENANT_ID`` prints what would run, writes
  nothing, and does not mark the action executed.

No live network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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


class TestT96VerifyTtlDryrun(unittest.TestCase):
    """Verify digests, stale-approve TTL, and dry-run execute."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t96_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        self._env = {**os.environ, "AEGIS_DATA_DIR": self._tmp}

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_APPROVE_TTL_HOURS", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _propose_and_get_digest(self, tenant_id: str) -> str:
        """Run ``propose TENANT_ID`` and return the payload_sha256 digest."""
        _write_profile(self._tmp, tenant_id, role="architect", goal="ship t96")
        code, stdout, stderr = _run_aegis("propose", tenant_id, env=self._env)
        self.assertEqual(code, 0, f"propose failed: {stderr!r}")
        digest_lines = [
            ln for ln in stdout.splitlines() if ln.startswith("payload_sha256:")
        ]
        self.assertEqual(len(digest_lines), 1)
        return digest_lines[0].split("payload_sha256:", 1)[1].strip()

    def _get_pending_action_id(self, tenant_id: str) -> str:
        """Return the action_id of the single pending action for tenant."""
        from core.twin_actions import list_actions

        actions = list_actions(tenant_id)
        pending = [a for a in actions if a.get("status") == "proposed"]
        self.assertEqual(len(pending), 1, f"expected 1 pending, got {pending!r}")
        return pending[0]["action_id"]

    # ------------------------------------------------------------------ #
    # 1) verify — mismatch exits 1
    # ------------------------------------------------------------------ #

    def test_verify_mismatch_exits_1(self) -> None:
        """``verify`` exits 1 when a stored digest differs from recomputed."""
        tenant = "t96_verify"
        _write_profile(self._tmp, tenant, role="architect", goal="ship t96")

        # Propose one action so we have a pending row.
        self._propose_and_get_digest(tenant)
        action_id = self._get_pending_action_id(tenant)

        # Corrupt the stored payload_sha256 so it no longer matches the
        # recomputed digest.
        from core.persistence import get_connection

        with get_connection() as conn:
            conn.execute(
                "UPDATE twin_actions SET payload_sha256 = ? WHERE action_id = ?",
                ("0" * 64, action_id),
            )

        code, stdout, stderr = _run_aegis("verify", tenant, env=self._env)
        self.assertEqual(code, 1, f"expected exit 1, got {code}: {stdout!r}")
        self.assertIn("mismatch", stdout)

    def test_verify_clean_exits_0(self) -> None:
        """``verify`` exits 0 when all digests match (sanity check)."""
        tenant = "t96_verify_clean"
        _write_profile(self._tmp, tenant, role="architect", goal="ship t96")
        self._propose_and_get_digest(tenant)

        code, stdout, stderr = _run_aegis("verify", tenant, env=self._env)
        self.assertEqual(code, 0, f"expected exit 0, got {code}: {stderr!r}")
        self.assertIn("ok", stdout)

    # ------------------------------------------------------------------ #
    # 2) stale approve cannot execute
    # ------------------------------------------------------------------ #

    def test_stale_approve_cannot_execute(self) -> None:
        """An approve older than TTL cannot execute; no receipt written."""
        tenant = "t96_ttl"
        _write_profile(self._tmp, tenant, role="architect", goal="ship t96")
        digest = self._propose_and_get_digest(tenant)
        action_id = self._get_pending_action_id(tenant)

        # Approve with the correct digest.
        from core.twin_actions import approve

        approve(action_id, tenant, "actor-t96", expected_payload_sha256=digest)

        # Backdate approved_at to 48 hours ago (TTL default = 24h).
        stale = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        from core.persistence import get_connection

        with get_connection() as conn:
            conn.execute(
                "UPDATE twin_actions SET approved_at = ? WHERE action_id = ?",
                (stale, action_id),
            )

        # Attempt execute — must raise PermissionError and not write receipt.
        from core.twin_actions import execute

        with self.assertRaises(PermissionError):
            execute(action_id, tenant)

        # Status must still be ``approved`` (not executed).
        from core.twin_actions import _load_action

        action = _load_action(action_id)
        assert action is not None
        self.assertEqual(action["status"], "approved")

        # No receipt file on disk.
        receipt_path = (
            Path(self._tmp) / "work_products" / tenant / "receipts" / f"{action_id}.md"
        )
        self.assertFalse(receipt_path.exists())

    def test_fresh_approve_can_execute(self) -> None:
        """A fresh approve (within TTL) executes normally."""
        tenant = "t96_ttl_fresh"
        _write_profile(self._tmp, tenant, role="architect", goal="ship t96")
        digest = self._propose_and_get_digest(tenant)
        action_id = self._get_pending_action_id(tenant)

        from core.twin_actions import approve, execute

        approve(action_id, tenant, "actor-t96", expected_payload_sha256=digest)
        result = execute(action_id, tenant)
        self.assertEqual(result["status"], "executed")

    # ------------------------------------------------------------------ #
    # 3) dry-run writes nothing
    # ------------------------------------------------------------------ #

    def test_dry_run_writes_nothing(self) -> None:
        """``execute --dry-run`` prints what would run, writes nothing,
        and does not mark the action executed."""
        tenant = "t96_dryrun"
        _write_profile(self._tmp, tenant, role="architect", goal="ship t96")
        digest = self._propose_and_get_digest(tenant)
        action_id = self._get_pending_action_id(tenant)

        # Approve so the action is executable.
        from core.twin_actions import approve

        approve(action_id, tenant, "actor-t96", expected_payload_sha256=digest)

        code, stdout, stderr = _run_aegis(
            "execute", "--dry-run", action_id, tenant, env=self._env,
        )
        self.assertEqual(code, 0, f"exit {code}: stdout={stdout!r} stderr={stderr!r}")
        self.assertIn("would execute", stdout)
        self.assertIn("writes: nothing", stdout)

        # Status must still be ``approved`` (not executed).
        from core.twin_actions import _load_action

        action = _load_action(action_id)
        assert action is not None
        self.assertEqual(action["status"], "approved")

        # No receipt file on disk.
        receipt_path = (
            Path(self._tmp) / "work_products" / tenant / "receipts" / f"{action_id}.md"
        )
        self.assertFalse(receipt_path.exists())

        # No audit line for the dry-run.
        audit_path = Path(self._tmp) / tenant / "audit.jsonl"
        if audit_path.exists():
            lines = [
                ln for ln in audit_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            for ln in lines:
                obj = json.loads(ln)
                self.assertNotEqual(
                    obj.get("kind"),
                    "execute",
                    "dry-run must not append an execute audit line",
                )


if __name__ == "__main__":
    unittest.main()
