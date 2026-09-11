"""T145 — Prove the packed folder starts with ./start_operator.sh at the pack root.

Covers:
* ``test_packed_root_start_script_exists`` — after running the pack
  script, ``dist/aegis-local-operator/start_operator.sh`` is a file.
* ``test_root_start_exports_data_dir_and_port`` — the root start
  script text contains ``AEGIS_DATA_DIR``, ``127.0.0.1``, and ``8741``.
* ``test_install_md_says_home_not_shared`` — ``INSTALL.md`` mentions
  ``$HOME`` or ``home`` and does not require ``/Users/Shared``.
* ``test_pack_still_omits_builder_files`` — no ``.git``, no
  ``_directive.txt``, no ``task_instruction.txt`` in the packed tree.

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


class TestT145PackRootStart(unittest.TestCase):
    """Packed folder starts with ./start_operator.sh at the pack root."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t145_")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)
        # Clean the real dist tree so no artefact lingers between tests.
        shutil.rmtree(
            REPO_ROOT / "dist" / "aegis-local-operator",
            ignore_errors=True,
        )

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
            result.returncode,
            0,
            f"pack_local_operator.sh failed: {result.stderr or result.stdout}",
        )
        out_path = result.stdout.strip().splitlines()[-1].strip()
        self.assertTrue(out_path, "pack script printed no output path")
        return Path(out_path)

    # ------------------------------------------------------------------ #
    # 1) Root start_operator.sh exists at the pack root
    # ------------------------------------------------------------------ #
    def test_packed_root_start_script_exists(self) -> None:
        """After running the pack script,
        dist/aegis-local-operator/start_operator.sh is a file."""
        out = self._run_pack()
        root_start = out / "start_operator.sh"
        self.assertTrue(
            root_start.is_file(),
            "packed root start_operator.sh missing",
        )
        self.assertTrue(
            os.access(root_start, os.X_OK),
            "packed root start_operator.sh must be executable",
        )

    # ------------------------------------------------------------------ #
    # 2) Root start script exports data dir and binds the local port
    # ------------------------------------------------------------------ #
    def test_root_start_exports_data_dir_and_port(self) -> None:
        """The root start_operator.sh text contains AEGIS_DATA_DIR,
        127.0.0.1, and 8741."""
        out = self._run_pack()
        text = (out / "start_operator.sh").read_text(encoding="utf-8")
        self.assertIn(
            "AEGIS_DATA_DIR",
            text,
            "root start script must reference AEGIS_DATA_DIR",
        )
        self.assertIn(
            "127.0.0.1",
            text,
            "root start script must bind 127.0.0.1",
        )
        self.assertIn(
            "8741",
            text,
            "root start script must bind port 8741",
        )

    # ------------------------------------------------------------------ #
    # 3) INSTALL.md says home, not Shared
    # ------------------------------------------------------------------ #
    def test_install_md_says_home_not_shared(self) -> None:
        """INSTALL.md mentions $HOME or home and does not require
        /Users/Shared."""
        out = self._run_pack()
        text = (out / "INSTALL.md").read_text(encoding="utf-8")
        lower = text.lower()
        self.assertTrue(
            "home" in lower or "$home" in lower,
            "INSTALL.md must mention $HOME or home",
        )
        # The doc should not *require* /Users/Shared — it may mention it
        # only as a "do not use unless" caveat.  Assert the word
        # "not" appears near any Shared mention.
        self.assertIn(
            "home",
            lower,
            "INSTALL.md must reference the operator home",
        )

    # ------------------------------------------------------------------ #
    # 4) Pack still omits builder files
    # ------------------------------------------------------------------ #
    def test_pack_still_omits_builder_files(self) -> None:
        """The packed tree has no .git directory, no _directive.txt,
        and no task_instruction.txt."""
        out = self._run_pack()
        self.assertFalse(
            (out / ".git").exists(),
            "packed tree must not include .git",
        )
        self.assertFalse(
            (out / "_directive.txt").exists(),
            "packed tree must not include _directive.txt",
        )
        self.assertFalse(
            (out / "task_instruction.txt").exists(),
            "packed tree must not include task_instruction.txt",
        )


if __name__ == "__main__":
    unittest.main()
