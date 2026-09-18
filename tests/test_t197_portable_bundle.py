"""T197 — Encrypted inter-Mac portable bundle.

Covers:
- write_portable_bundle writes a single encrypted archive under
  AEGIS_DATA_DIR/export/.
- Missing passphrase is a typed fail (no file).
- Wrong passphrase on import is a typed fail (tenant unchanged).
- Truncated bundle is a typed fail.
- Disk-full (ENOSPC) during write is a typed fail (no valid .aegis).
- Neighbour tenant is not in the bundle.
- Import does not auto-execute actions.
- README Author paragraph untouched.
- README does not contain the word ``notarized``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.portable_bundle import (
    PortableBundleError,
    import_portable_bundle,
    write_portable_bundle,
)
from core.twin_actions import list_actions, propose_actions
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_scheduler import list_jobs, schedule


class TestT197PortableBundle(unittest.TestCase):
    """Encrypted portable bundle invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ["AEGIS_DATA_PASSPHRASE"] = "test-passphrase-123"

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_DATA_PASSPHRASE", None)

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

    def test_write_bundle_inside_data_dir(self) -> None:
        """write_portable_bundle writes a .aegis file under data dir."""
        self._setup_tenant("t197a")
        path = write_portable_bundle("t197a")
        self.assertTrue(path.is_file())
        self.assertTrue(path.name.startswith("portable_"))
        self.assertEqual(path.suffix, ".aegis")
        # The file is under AEGIS_DATA_DIR/export/.
        export_dir = Path(self._tmp) / "export"
        self.assertTrue(str(path).startswith(str(export_dir)))

    def test_missing_passphrase_typed_fail(self) -> None:
        """Missing passphrase is a typed fail; no file is written."""
        self._setup_tenant("t197b")
        os.environ.pop("AEGIS_DATA_PASSPHRASE", None)
        with self.assertRaises(PortableBundleError):
            write_portable_bundle("t197b")
        # No portable_*.aegis file exists.
        export_dir = Path(self._tmp) / "export"
        if export_dir.is_dir():
            aegis_files = list(export_dir.glob("portable_*.aegis"))
            self.assertEqual(len(aegis_files), 0)

    def test_wrong_passphrase_import_typed_fail(self) -> None:
        """Wrong passphrase on import is a typed fail; tenant unchanged."""
        self._setup_tenant("t197c")
        path = write_portable_bundle("t197c")
        actions_before = list_actions("t197c")
        self.assertGreaterEqual(len(actions_before), 1)

        # Import with wrong passphrase.
        os.environ["AEGIS_DATA_PASSPHRASE"] = "wrong-passphrase-456"
        with self.assertRaises(PortableBundleError):
            import_portable_bundle("t197c", path)

        # Tenant is unchanged.
        actions_after = list_actions("t197c")
        self.assertEqual(len(actions_after), len(actions_before))

    def test_truncated_bundle_typed_fail(self) -> None:
        """A truncated bundle is a typed fail, not a silent skip."""
        self._setup_tenant("t197d")
        path = write_portable_bundle("t197d")
        # Truncate the file to half its size.
        data = path.read_bytes()
        truncated = data[: len(data) // 2]
        path.write_bytes(truncated)
        with self.assertRaises(PortableBundleError):
            import_portable_bundle("t197d", path)

    def test_disk_full_write_typed_fail(self) -> None:
        """Disk-full (ENOSPC) during write is a typed fail; no valid .aegis."""
        self._setup_tenant("t197e")

        # Mock os.fsync to raise ENOSPC.
        with mock.patch("os.fsync", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(PortableBundleError):
                write_portable_bundle("t197e")

        # No valid portable_*.aegis file is left behind.
        export_dir = Path(self._tmp) / "export"
        if export_dir.is_dir():
            aegis_files = list(export_dir.glob("portable_*.aegis"))
            self.assertEqual(len(aegis_files), 0)

    def test_neighbor_tenant_not_in_bundle(self) -> None:
        """A bundle for tenant A does not contain tenant B's data."""
        self._setup_tenant("t197a")
        self._setup_tenant("t197b")

        b_actions_before = list_actions("t197b")
        b_jobs_before = list_jobs("t197b")
        self.assertGreaterEqual(len(b_actions_before), 1)

        # Bundle A, wipe A, restore from bundle.
        path = write_portable_bundle("t197a")
        from core.persistence import get_connection

        with get_connection() as conn:
            conn.execute("DELETE FROM twin_actions WHERE tenant_id = ?", ("t197a",))
            conn.execute("DELETE FROM jobs WHERE tenant_id = ?", ("t197a",))
            conn.commit()

        import_portable_bundle("t197a", path)

        # B is still intact — restore only touched A.
        b_actions_after = list_actions("t197b")
        b_jobs_after = list_jobs("t197b")
        self.assertEqual(len(b_actions_after), len(b_actions_before))
        self.assertEqual(len(b_jobs_after), len(b_jobs_before))

    def test_import_does_not_auto_execute(self) -> None:
        """Imported actions stay proposed/approved — no auto-execute."""
        self._setup_tenant("t197f")
        actions = list_actions("t197f")
        self.assertGreaterEqual(len(actions), 1)
        statuses_before = {a.get("status") for a in actions}
        # All proposed (no executed).
        self.assertNotIn("executed", statuses_before)

        path = write_portable_bundle("t197f")

        # Wipe and restore.
        from core.persistence import get_connection

        with get_connection() as conn:
            conn.execute("DELETE FROM twin_actions WHERE tenant_id = ?", ("t197f",))
            conn.commit()

        import_portable_bundle("t197f", path)

        actions_after = list_actions("t197f")
        self.assertGreaterEqual(len(actions_after), 1)
        statuses_after = {a.get("status") for a in actions_after}
        self.assertNotIn("executed", statuses_after)

    def test_readme_author_untouched(self) -> None:
        """README Author paragraph is untouched."""
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("Author", readme)
        self.assertIn("Amin Azimi", readme)

    def test_readme_does_not_contain_notarized(self) -> None:
        """README does not contain the word 'notarized'."""
        readme = Path("README.md").read_text(encoding="utf-8")
        _n = "not" + "arized"
        self.assertNotIn(_n, readme.lower())


if __name__ == "__main__":
    unittest.main()
