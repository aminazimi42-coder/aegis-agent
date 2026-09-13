"""T172 — Stranger giveable pack: home copy and optional venv.

Covers:

* ``test_build_or_pack_script_exists`` — the build or pack script exists
  and is executable.
* ``test_pack_root_start_script_names_data_dir_and_port`` — after running
  the pack script, the root ``start_operator.sh`` mentions
  ``AEGIS_DATA_DIR`` (or ``$HOME/.aegis``) and port ``8741``.
* ``test_install_command_names_home_not_shared`` — ``Install.command``
  in the installer folder references ``$HOME`` and does not require
  ``/Users/Shared``.
* ``test_install_command_does_not_open_safari`` — ``Install.command``
  does not call the ``open`` shell command to launch a browser.
* ``test_pack_omits_git_and_directive`` — the packed tree contains no
  ``.git`` and no ``_directive.txt``.
* ``test_readme_does_not_claim_notarized`` — the repo README does not
  claim the installer is notarized in the Now section.
* ``test_readme_author_untouched`` — the Author paragraph is present
  and names Amin Azimi.

No uvicorn is started.  No live network is used.  Build only.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_mac_installer.sh"
PACK_SCRIPT = REPO_ROOT / "scripts" / "pack_local_operator.sh"


class TestT172StrangerPack(unittest.TestCase):
    """Stranger pack rebuilds with home copy and optional venv."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t172_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        shutil.rmtree(self._tmp, ignore_errors=True)
        shutil.rmtree(
            REPO_ROOT / "dist" / "aegis-local-operator",
            ignore_errors=True,
        )
        shutil.rmtree(
            REPO_ROOT / "dist" / "AegisOperator-mac",
            ignore_errors=True,
        )

    # ------------------------------------------------------------------ #
    # helper: run the build and return the installer folder path
    # ------------------------------------------------------------------ #
    def _run_build(self) -> Path:
        env = dict(os.environ)
        env["AEGIS_DATA_DIR"] = self._tmp
        result = subprocess.run(
            ["/bin/sh", str(BUILD_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"build_mac_installer.sh failed: {result.stderr or result.stdout}",
        )
        out_path = result.stdout.strip().splitlines()[-1].strip()
        self.assertTrue(out_path, "build script printed no output path")
        return Path(out_path)

    # ------------------------------------------------------------------ #
    # 1) Build or pack script exists
    # ------------------------------------------------------------------ #
    def test_build_or_pack_script_exists(self) -> None:
        """scripts/build_mac_installer.sh and
        scripts/pack_local_operator.sh both exist and are
        executable."""
        self.assertTrue(
            BUILD_SCRIPT.is_file(),
            "build_mac_installer.sh not found",
        )
        self.assertTrue(
            os.access(BUILD_SCRIPT, os.X_OK),
            "build_mac_installer.sh must be executable",
        )
        self.assertTrue(
            PACK_SCRIPT.is_file(),
            "pack_local_operator.sh not found",
        )
        self.assertTrue(
            os.access(PACK_SCRIPT, os.X_OK),
            "pack_local_operator.sh must be executable",
        )

    # ------------------------------------------------------------------ #
    # 2) Pack root start_operator.sh names data dir and port
    # ------------------------------------------------------------------ #
    def test_pack_root_start_script_names_data_dir_and_port(self) -> None:
        """The packed root start_operator.sh references AEGIS_DATA_DIR
        (or $HOME/.aegis) and port 8741."""
        out = self._run_build()
        root_start = out / "aegis-local-operator" / "start_operator.sh"
        self.assertTrue(
            root_start.is_file(),
            "pack root must contain start_operator.sh",
        )
        text = root_start.read_text(encoding="utf-8")
        self.assertIn(
            "AEGIS_DATA_DIR",
            text,
            "start_operator.sh must reference AEGIS_DATA_DIR",
        )
        self.assertIn(
            "8741",
            text,
            "start_operator.sh must reference port 8741",
        )

    # ------------------------------------------------------------------ #
    # 3) Install.command names $HOME, not /Users/Shared
    # ------------------------------------------------------------------ #
    def test_install_command_names_home_not_shared(self) -> None:
        """Install.command references $HOME and does not require
        /Users/Shared."""
        out = self._run_build()
        cmd_text = (out / "Install.command").read_text(encoding="utf-8")
        self.assertIn(
            "$HOME",
            cmd_text,
            "Install.command must reference $HOME",
        )
        self.assertNotIn(
            "/Users/Shared",
            cmd_text,
            "Install.command must not require /Users/Shared",
        )

    # ------------------------------------------------------------------ #
    # 4) Install.command does not open a browser
    # ------------------------------------------------------------------ #
    def test_install_command_does_not_open_safari(self) -> None:
        """Install.command does not call the open shell command to
        launch a browser.  It may print 'open http://…' as an
        instruction to the operator — filter to code lines and check
        for the open command, not the echo text."""
        out = self._run_build()
        cmd_text = (out / "Install.command").read_text(encoding="utf-8")
        code_lines = [
            line
            for line in cmd_text.splitlines()
            if line.strip()
            and not line.strip().startswith("#")
        ]
        code_text = "\n".join(code_lines)
        self.assertNotRegex(
            code_text,
            r"(^|\n|\s)open\s",
            "Install.command must not call the open command to launch a browser",
        )

    # ------------------------------------------------------------------ #
    # 5) Pack omits .git and _directive.txt
    # ------------------------------------------------------------------ #
    def test_pack_omits_git_and_directive(self) -> None:
        """The installer folder contains no .git and no
        _directive.txt."""
        out = self._run_build()
        self.assertFalse(
            (out / ".git").exists(),
            "installer must not include .git",
        )
        self.assertFalse(
            (out / "_directive.txt").exists(),
            "installer must not include _directive.txt",
        )
        # Also check the packed tree inside.
        pack = out / "aegis-local-operator"
        self.assertFalse(
            (pack / ".git").exists(),
            "pack must not include .git",
        )
        self.assertFalse(
            (pack / "_directive.txt").exists(),
            "pack must not include _directive.txt",
        )

    # ------------------------------------------------------------------ #
    # 6) README does not claim notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_claim_notarized(self) -> None:
        """The repo README does not use the word 'notarized' in the
        Now section (it is honest about being unsigned)."""
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        # The Now section is between '## Now' and '---' before Planned.
        now_match = re.search(
            r"## Now\s*\n(.*?)(?=\n---\s*\n)",
            text,
            re.DOTALL,
        )
        assert now_match is not None, "README must have a Now section"
        now_section = now_match.group(1)
        self.assertNotIn(
            "notarized",
            now_section.lower(),
            "README Now must not claim the installer is notarized",
        )

    # ------------------------------------------------------------------ #
    # 7) README Author paragraph is untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The Author paragraph names Amin Azimi and is present."""
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Author", text, "README must have an Author section")
        author_match = re.search(
            r"## Author\s*\n(.*)",
            text,
            re.DOTALL,
        )
        assert author_match is not None, "Author section must have content"
        author_text = author_match.group(1)
        self.assertIn(
            "Amin Azimi",
            author_text,
            "Author paragraph must name Amin Azimi",
        )


if __name__ == "__main__":
    unittest.main()
