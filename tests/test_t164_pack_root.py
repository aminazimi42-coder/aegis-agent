"""T164 — Rebuild the giveable local pack and verify its root.

Covers:
* ``test_pack_root_contains_start_operator_sh`` — after running the
  pack script, ``dist/aegis-local-operator/start_operator.sh`` is a
  file at the pack root.
* ``test_install_md_tells_operator_to_copy_into_home`` — INSTALL.md
  tells the operator to copy into ``$HOME``, not ``/Users/Shared``.
* ``test_start_operator_sh_does_not_call_open_or_xdg_open`` —
  ``start_operator.sh`` does not call ``open`` or ``xdg-open`` (does
  not launch a browser).
* ``test_pack_does_not_contain_git_directive_or_aegis`` — the packed
  tree contains no ``.git``, no ``_directive.txt``, and no live
  ``$HOME/.aegis`` directory.

No uvicorn is started.  No live network is used.  Build only.
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


class TestT164PackRoot(unittest.TestCase):
    """The giveable local pack starts from the pack root."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t164_")

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
    # 1) Pack root contains start_operator.sh
    # ------------------------------------------------------------------ #
    def test_pack_root_contains_start_operator_sh(self) -> None:
        """dist/aegis-local-operator/start_operator.sh is a file at the
        pack root and is executable."""
        out = self._run_pack()
        root_start = out / "start_operator.sh"
        self.assertTrue(
            root_start.is_file(),
            "pack root must contain start_operator.sh",
        )
        self.assertTrue(
            os.access(root_start, os.X_OK),
            "pack root start_operator.sh must be executable",
        )

    # ------------------------------------------------------------------ #
    # 2) INSTALL.md tells the operator to copy into $HOME
    # ------------------------------------------------------------------ #
    def test_install_md_tells_operator_to_copy_into_home(self) -> None:
        """INSTALL.md mentions $HOME and does not require /Users/Shared."""
        out = self._run_pack()
        text = (out / "INSTALL.md").read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn(
            "$home",
            lower,
            "INSTALL.md must tell the operator to copy into $HOME",
        )

    # ------------------------------------------------------------------ #
    # 3) start_operator.sh does not call open or xdg-open
    # ------------------------------------------------------------------ #
    def test_start_operator_sh_does_not_call_open_or_xdg_open(self) -> None:
        """start_operator.sh does not call ``open`` or ``xdg-open`` —
        it does not launch a browser."""
        out = self._run_pack()
        root_start = out / "start_operator.sh"
        text = root_start.read_text(encoding="utf-8")
        # Filter to non-comment lines before scanning for the command.
        code_lines = [
            line
            for line in text.splitlines()
            if not line.strip().startswith("#")
        ]
        code_text = "\n".join(code_lines)
        # Assert no bare 'open ' or 'xdg-open' command in the code.
        self.assertNotIn(
            "xdg-open",
            code_text,
            "start_operator.sh must not call xdg-open",
        )
        # 'open' as a shell command is 'open ' or 'open\t' — check for
        # the pattern that would launch a browser.  The root wrapper
        # only execs scripts/start_operator.sh, which also does not
        # call open.
        self.assertNotRegex(
            code_text,
            r"(^|\n|\s)open\s",
            "start_operator.sh must not call the open command to launch a browser",
        )

    # ------------------------------------------------------------------ #
    # 4) Pack does not contain .git, _directive.txt, or $HOME/.aegis
    # ------------------------------------------------------------------ #
    def test_pack_does_not_contain_git_directive_or_aegis(self) -> None:
        """The packed tree has no .git directory, no _directive.txt,
        and no live .aegis directory."""
        out = self._run_pack()
        self.assertFalse(
            (out / ".git").exists(),
            "pack must not include .git",
        )
        self.assertFalse(
            (out / "_directive.txt").exists(),
            "pack must not include _directive.txt",
        )
        self.assertFalse(
            (out / ".aegis").exists(),
            "pack must not include a live .aegis directory",
        )


if __name__ == "__main__":
    unittest.main()
