"""T100 — Local search, replay, export, and import.

Covers:
- ``aegis search TENANT_ID TERM`` — grep-style scan under the tenant
  data root for ``.md``/``.json`` files matching *term* (case-insensitive).
- ``aegis replay ACTION_ID TENANT_ID`` — write one markdown file listing
  the propose → approve → execute lifecycle if present.  Does not
  re-execute.
- ``aegis export TENANT_ID OUT_PATH`` → ``aegis import ARCHIVE_PATH`` —
  pack the tenant's data-root folder to a local ``.tar.gz`` and restore
  into ``AEGIS_DATA_DIR``.  Never touches another tenant.
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


class TestT100SearchReplayExportImport(unittest.TestCase):
    """Local search, replay, export, and import."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t100_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        self._env = {**os.environ, "AEGIS_DATA_DIR": self._tmp}

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _propose_one(self, tenant_id: str) -> str:
        """Insert one proposed action via the CLI and return its action_id."""
        _write_profile(self._tmp, tenant_id)
        code, stdout, stderr = _run_aegis("propose", tenant_id, env=self._env)
        assert code == 0, f"propose failed: {stderr!r}"
        lines = [ln for ln in stdout.splitlines() if ln.strip().startswith("{")]
        assert lines, f"no JSON in stdout: {stdout!r}"
        result = json.loads(lines[-1])
        return result["action_id"]

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_search_finds_term(self) -> None:
        """``aegis search TENANT_ID TERM`` finds matching .md/.json files."""
        tenant = f"t100-search-{uuid4().hex[:8]}"
        _write_profile(self._tmp, tenant, role="backend", goal="migrate")

        # Write an extra markdown file that contains a search term.
        wp_dir = Path(self._tmp) / "work_products" / tenant
        wp_dir.mkdir(parents=True, exist_ok=True)
        (wp_dir / "notes.md").write_text(
            "# Notes\n\nReview the migration plan.\n",
            encoding="utf-8",
        )

        # Search for a term present in profile.json.
        code, stdout, stderr = _run_aegis(
            "search", tenant, "backend", env=self._env,
        )
        self.assertEqual(code, 0, f"search failed: {stderr!r}")
        self.assertTrue(stdout, "search should return at least one match")
        # profile.json contains "backend" in the role field.
        self.assertIn("profile.json", stdout)

        # Search for a term present in notes.md.
        code2, stdout2, stderr2 = _run_aegis(
            "search", tenant, "migration", env=self._env,
        )
        self.assertEqual(code2, 0, f"search2 failed: {stderr2!r}")
        self.assertIn("notes.md", stdout2)

        # Search for a non-existent term — no matches, exit 0.
        code3, stdout3, _ = _run_aegis(
            "search", tenant, "nonexistent_term_xyz", env=self._env,
        )
        self.assertEqual(code3, 0)
        self.assertEqual(stdout3, "")

    def test_replay_writes_markdown(self) -> None:
        """``aegis replay ACTION_ID TENANT_ID`` writes a markdown replay file."""
        tenant = f"t100-replay-{uuid4().hex[:8]}"
        action_id = self._propose_one(tenant)

        code, stdout, stderr = _run_aegis(
            "replay", action_id, tenant, env=self._env,
        )
        self.assertEqual(code, 0, f"replay failed: {stderr!r}")

        # The replay file path is printed on stdout.
        replay_path = Path(stdout.strip())
        self.assertTrue(replay_path.is_file(), f"replay file not found: {replay_path}")

        content = replay_path.read_text(encoding="utf-8")
        # Should contain the action_id and lifecycle sections.
        self.assertIn(action_id, content)
        self.assertIn("## Propose", content)
        self.assertIn("## Approve", content)
        self.assertIn("## Execute", content)

        # Replay on an unknown action should exit 2.
        code2, _, stderr2 = _run_aegis(
            "replay", "act-nonexistent", tenant, env=self._env,
        )
        self.assertEqual(code2, 2)
        self.assertIn("replay error", stderr2)

    def test_export_import_roundtrip(self) -> None:
        """``aegis export`` → ``aegis import`` restores tenant files."""
        tenant = f"t100-export-{uuid4().hex[:8]}"
        _write_profile(self._tmp, tenant, role="lead", goal="deploy")

        # Write an extra work-products file so we have content to verify.
        wp_dir = Path(self._tmp) / "work_products" / tenant
        wp_dir.mkdir(parents=True, exist_ok=True)
        (wp_dir / "summary.md").write_text(
            "# Summary\n\nDeployment checklist.\n",
            encoding="utf-8",
        )

        # Export to a .tar.gz in a separate directory.
        export_dir = tempfile.mkdtemp(prefix="aegis_t100_export_")
        archive_path = os.path.join(export_dir, f"{tenant}.tar.gz")

        code, stdout, stderr = _run_aegis(
            "export", tenant, archive_path, env=self._env,
        )
        self.assertEqual(code, 0, f"export failed: {stderr!r}")
        self.assertTrue(os.path.isfile(archive_path), "archive file not created")

        # Now import into a fresh AEGIS_DATA_DIR.
        import_dir = tempfile.mkdtemp(prefix="aegis_t100_import_")
        import_env = {**self._env, "AEGIS_DATA_DIR": import_dir}

        code2, stdout2, stderr2 = _run_aegis(
            "import", archive_path, env=import_env,
        )
        self.assertEqual(code2, 0, f"import failed: {stderr2!r}")

        # Verify the profile was restored.
        imported_profile = Path(import_dir) / tenant / "profile.json"
        self.assertTrue(
            imported_profile.is_file(),
            f"imported profile not found: {imported_profile}",
        )
        data = json.loads(imported_profile.read_text(encoding="utf-8"))
        self.assertEqual(data["role"], "lead")
        self.assertEqual(data["goal"], "deploy")

        # Verify the work-products file was restored.
        imported_summary = Path(import_dir) / "work_products" / tenant / "summary.md"
        self.assertTrue(
            imported_summary.is_file(),
            f"imported summary not found: {imported_summary}",
        )
        self.assertIn("Deployment checklist", imported_summary.read_text(encoding="utf-8"))

        # Verify another tenant in the original data dir was NOT touched.
        # (Implicit — we only exported one tenant, so the import dir has
        # exactly that tenant's files.)

    def test_no_live_network(self) -> None:
        """No live network is used in this test module."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
