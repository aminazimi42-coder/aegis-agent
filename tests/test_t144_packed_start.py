"""T144 — Prove the Layer-1 pack starts from a copied folder.

Covers:
* ``test_pack_script_builds_folder`` — running the pack script produces
  ``dist/aegis-local-operator/scripts/start_operator.sh``.
* ``test_packed_start_exports_data_dir_and_port`` — the packed start
  script exports ``AEGIS_DATA_DIR`` and binds ``127.0.0.1`` and ``8741``.
* ``test_pack_omits_builder_files`` — the packed tree contains no
  ``.git`` directory, no ``_directive.txt``, no ``task_instruction.txt``.
* ``test_install_md_present`` — ``INSTALL.md`` is present in the pack.

No uvicorn is started.  No live network is used.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACK_SCRIPT = REPO_ROOT / "scripts" / "pack_local_operator.sh"


class TestT144PackedStart(unittest.TestCase):
    """Layer-1 packed operator starts without builder files."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t144_")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)
        # Clean the real dist tree so no artefact lingers between tests.
        shutil.rmtree(REPO_ROOT / "dist" / "aegis-local-operator",
                      ignore_errors=True)

    # ------------------------------------------------------------------ #
    # helper: run the pack once and return the output folder path
    # ------------------------------------------------------------------ #
    def _run_pack(self) -> Path:
        env = dict(os.environ)
        env["AEGIS_DATA_DIR"] = self._tmp
        result = subprocess.run(
            ["/bin/sh", str(PACK_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode, 0,
            f"pack_local_operator.sh failed: {result.stderr or result.stdout}",
        )
        out_path = result.stdout.strip().splitlines()[-1].strip()
        self.assertTrue(out_path, "pack script printed no output path")
        return Path(out_path)

    # ------------------------------------------------------------------ #
    # 1) Pack script builds the folder
    # ------------------------------------------------------------------ #
    def test_pack_script_builds_folder(self) -> None:
        """Running the pack script produces a folder with
        scripts/start_operator.sh inside it."""
        out = self._run_pack()
        start = out / "scripts" / "start_operator.sh"
        self.assertTrue(start.is_file(),
                        "packed scripts/start_operator.sh missing")
        # The packed start script must be executable.
        self.assertTrue(os.access(start, os.X_OK),
                        "packed start_operator.sh must be executable")

    # ------------------------------------------------------------------ #
    # 2) Packed start script exports data dir and binds the local port
    # ------------------------------------------------------------------ #
    def test_packed_start_exports_data_dir_and_port(self) -> None:
        """The packed start_operator.sh text contains AEGIS_DATA_DIR,
        127.0.0.1, and 8741."""
        out = self._run_pack()
        text = (out / "scripts" / "start_operator.sh").read_text(
            encoding="utf-8",
        )
        self.assertIn("AEGIS_DATA_DIR", text,
                      "packed start script must export AEGIS_DATA_DIR")
        self.assertIn("127.0.0.1", text,
                      "packed start script must bind 127.0.0.1")
        self.assertIn("8741", text,
                      "packed start script must bind port 8741")

    # ------------------------------------------------------------------ #
    # 3) Pack omits builder files
    # ------------------------------------------------------------------ #
    def test_pack_omits_builder_files(self) -> None:
        """The packed tree has no .git directory, no _directive.txt,
        and no task_instruction.txt."""
        out = self._run_pack()
        self.assertFalse((out / ".git").exists(),
                        "packed tree must not include .git")
        self.assertFalse((out / "_directive.txt").exists(),
                        "packed tree must not include _directive.txt")
        self.assertFalse((out / "task_instruction.txt").exists(),
                        "packed tree must not include task_instruction.txt")

    # ------------------------------------------------------------------ #
    # 4) INSTALL.md present
    # ------------------------------------------------------------------ #
    def test_install_md_present(self) -> None:
        """INSTALL.md is present in the packed folder."""
        out = self._run_pack()
        install_md = out / "INSTALL.md"
        self.assertTrue(install_md.is_file(),
                        "packed tree must include INSTALL.md")


if __name__ == "__main__":
    unittest.main()
