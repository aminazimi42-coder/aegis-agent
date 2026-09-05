"""T69 — Local SQLite backup and restore for a single tenant.

Covers:
- backup_tenant writes a .zip archive under AEGIS_DATA_DIR.
- restore_tenant restores the tenant's rows from the archive.
- A roundtrip backup→wipe→restore preserves profile, actions, jobs, and
  receipt files for the backed-up tenant.
- Neighbour tenants are untouched by a restore.
- No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_actions import list_actions, propose_actions
from core.twin_backup import backup_tenant, restore_tenant
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_scheduler import list_jobs, schedule


class TestT69BackupRestore(unittest.TestCase):
    """Local tenant backup/restore invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> None:
        """Run a complete T03 interview+commit so a profile exists."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)

    def _setup_tenant(self, tenant_id: str) -> None:
        """Create profile + actions + jobs for *tenant_id*."""
        self._full_interview(tenant_id)
        propose_actions(tenant_id)
        schedule(tenant_id, "weekly review", "2026-01-01T10:00:00Z")

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_backup_then_restore_roundtrip(self) -> None:
        """Backup, wipe, restore — all tenant data comes back."""
        self._setup_tenant("t69a")

        # Capture counts before backup.
        actions_before = list_actions("t69a")
        jobs_before = list_jobs("t69a")
        self.assertGreaterEqual(len(actions_before), 1)
        self.assertGreaterEqual(len(jobs_before), 1)

        # Backup.
        dest = Path(self._tmp) / "t69a_backup.zip"
        archive = backup_tenant("t69a", dest)
        self.assertTrue(archive.exists())
        self.assertEqual(archive.suffix, ".zip")

        # Wipe the tenant by deleting rows.
        from core.persistence import get_connection

        with get_connection() as conn:
            conn.execute("DELETE FROM twin_actions WHERE tenant_id = ?", ("t69a",))
            conn.execute("DELETE FROM jobs WHERE tenant_id = ?", ("t69a",))
            conn.commit()

        # Verify wipe.
        self.assertEqual(len(list_actions("t69a")), 0)
        self.assertEqual(len(list_jobs("t69a")), 0)

        # Restore.
        result = restore_tenant("t69a", archive)
        self.assertEqual(result["tenant_id"], "t69a")

        # Verify data is back.
        actions_after = list_actions("t69a")
        jobs_after = list_jobs("t69a")
        self.assertEqual(len(actions_after), len(actions_before))
        self.assertEqual(len(jobs_after), len(jobs_before))

        # Action IDs preserved.
        before_ids = {a["action_id"] for a in actions_before}
        after_ids = {a["action_id"] for a in actions_after}
        self.assertEqual(before_ids, after_ids)

    def test_neighbor_untouched(self) -> None:
        """Restoring tenant A does not affect tenant B's data."""
        self._setup_tenant("t69a")
        self._setup_tenant("t69b")

        # Capture B's state before restore.
        b_actions_before = list_actions("t69b")
        b_jobs_before = list_jobs("t69b")
        self.assertGreaterEqual(len(b_actions_before), 1)
        self.assertGreaterEqual(len(b_jobs_before), 1)

        # Backup and wipe A only.
        dest = Path(self._tmp) / "t69a_backup.zip"
        archive = backup_tenant("t69a", dest)

        from core.persistence import get_connection

        with get_connection() as conn:
            conn.execute("DELETE FROM twin_actions WHERE tenant_id = ?", ("t69a",))
            conn.commit()

        # B is still intact.
        self.assertEqual(len(list_actions("t69b")), len(b_actions_before))

        # Restore A.
        restore_tenant("t69a", archive)

        # B's data is unchanged.
        b_actions_after = list_actions("t69b")
        b_jobs_after = list_jobs("t69b")
        self.assertEqual(len(b_actions_after), len(b_actions_before))
        self.assertEqual(len(b_jobs_after), len(b_jobs_before))

        # B's action IDs are intact.
        before_ids = {a["action_id"] for a in b_actions_before}
        after_ids = {a["action_id"] for a in b_actions_after}
        self.assertEqual(before_ids, after_ids)

        # A is restored.
        self.assertGreaterEqual(len(list_actions("t69a")), 1)

    def test_backup_includes_receipts(self) -> None:
        """Backup captures receipt files and restore writes them back."""
        self._full_interview("t69r")
        # Propose + approve + execute to create a receipt file.
        actions = propose_actions("t69r")
        self.assertGreaterEqual(len(actions), 1)
        action = actions[0]

        from core.twin_actions import _action_digest, approve, execute

        digest = _action_digest(action)
        approve(
            action["action_id"],
            tenant_id="t69r",
            actor_id="tester",
            expected_payload_sha256=digest,
        )
        execute(action["action_id"], tenant_id="t69r")

        # Receipt file exists.
        receipts_dir = Path(self._tmp) / "work_products" / "t69r" / "receipts"
        receipt_file = receipts_dir / f"{action['action_id']}.md"
        self.assertTrue(receipt_file.exists())

        # Backup.
        dest = Path(self._tmp) / "t69r_backup.zip"
        archive = backup_tenant("t69r", dest)
        self.assertTrue(archive.exists())

        # Delete the receipt from disk.
        receipt_file.unlink()
        self.assertFalse(receipt_file.exists())

        # Restore.
        result = restore_tenant("t69r", archive)
        self.assertGreaterEqual(result["receipts"], 1)

        # Receipt is back on disk.
        self.assertTrue(receipt_file.exists())


if __name__ == "__main__":
    unittest.main()
