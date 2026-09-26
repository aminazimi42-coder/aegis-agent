"""T227 — Stranger Mac install without Terminal.

Covers:

* ``test_pack_root_has_install_command_and_app`` — after running the
  build script, ``dist/AegisOperator-mac/`` contains ``Install.command``
  and the ``Aegis Operator.app`` bundle (or a documented wrapper).
* ``test_data_dir_is_home_not_repo`` — the start path inside the
  installer folder sets ``AEGIS_DATA_DIR`` to ``$HOME/.aegis``, not to
  a path inside the repo or the builder worktree.
* ``test_missing_python_is_typed_not_crash`` — when ``python3.11`` is
  not on ``PATH``, ``Install.command`` prints a typed English message
  naming the official ``3.11.9`` macos11 ``.pkg`` URL from python.org
  and exits non-zero — it does not crash and does not auto-download.
* ``test_install_command_does_not_open_safari`` — ``Install.command``
  does not contain a ``Safari`` launch or ``open -a`` call.
* ``test_no_stripe_token_in_core`` — no ``*.py`` file under ``core/``
  contains the token ``stripe`` (case-insensitive).
* ``test_readme_now_names_double_click_path_not_notarized`` — the
  README ``## Now`` section names the double-click ``Install.command``
  path and does not claim the installer is notarized.

No uvicorn subprocess.  No live network.  Build and read only.
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


class TestT227StrangerInstall(unittest.TestCase):
    """Stranger Mac install via double-click only."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t227_")
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
    # helper: run the build once and return the installer folder path
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
    # 1) Pack root has Install.command and the .app bundle
    # ------------------------------------------------------------------ #
    def test_pack_root_has_install_command_and_app(self) -> None:
        """The installer folder contains Install.command and
        Aegis Operator.app (or a documented wrapper)."""
        out = self._run_build()
        self.assertTrue(
            (out / "Install.command").is_file(),
            "installer folder missing Install.command",
        )
        self.assertTrue(
            os.access(out / "Install.command", os.X_OK),
            "Install.command must be executable",
        )
        app = out / "Aegis Operator.app"
        self.assertTrue(
            app.is_dir(),
            "installer folder missing Aegis Operator.app",
        )
        self.assertTrue(
            (app / "Contents" / "MacOS" / "AegisOperator").is_file(),
            "Aegis Operator.app missing MacOS/AegisOperator stub",
        )

    # ------------------------------------------------------------------ #
    # 2) Data dir is $HOME/.aegis, not a repo path
    # ------------------------------------------------------------------ #
    def test_data_dir_is_home_not_repo(self) -> None:
        """The start path sets AEGIS_DATA_DIR to $HOME/.aegis,
        not to a path inside the repo."""
        out = self._run_build()
        # Install.command references $HOME/.aegis
        cmd_text = (out / "Install.command").read_text(encoding="utf-8")
        self.assertIn(
            "$HOME/.aegis",
            cmd_text,
            "Install.command must set data dir to $HOME/.aegis",
        )
        # The .app stub also defaults to $HOME/.aegis
        stub = (
            out
            / "Aegis Operator.app"
            / "Contents"
            / "MacOS"
            / "AegisOperator"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "$HOME/.aegis",
            stub,
            "Aegis Operator.app stub must default AEGIS_DATA_DIR to $HOME/.aegis",
        )

    # ------------------------------------------------------------------ #
    # 3) Missing python3.11 is typed, not a crash
    # ------------------------------------------------------------------ #
    def test_missing_python_is_typed_not_crash(self) -> None:
        """When python3.11 is not on PATH, Install.command prints a
        typed English message naming the official 3.11.9 macos11 .pkg
        URL from python.org and exits non-zero.  It does not crash
        and does not auto-download."""
        out = self._run_build()
        cmd_text = (out / "Install.command").read_text(encoding="utf-8")
        # The script must contain the missing-python branch.
        self.assertIn(
            "python3.11 not found",
            cmd_text,
            "Install.command must have a typed missing-python3.11 branch",
        )
        # It must name the official 3.11.9 macos11 pkg URL.
        self.assertIn(
            "3.11.9",
            cmd_text,
            "Install.command must name Python 3.11.9",
        )
        self.assertIn(
            "macos11",
            cmd_text,
            "Install.command must name the macos11 .pkg",
        )
        self.assertIn(
            "python.org",
            cmd_text,
            "Install.command must name python.org as the source",
        )
        # It must exit non-zero (exit 1) on that branch.
        self.assertRegex(
            cmd_text,
            r"exit\s+1",
            "Install.command must exit non-zero on missing python",
        )

        # Actually run Install.command in a temp home with no
        # python3.11 on PATH and confirm the typed message prints
        # and the exit code is non-zero.
        temp_home = tempfile.mkdtemp(prefix="aegis_t227_home_")
        try:
            # Do NOT pre-create $HOME/aegis-local-operator — let
            # Install.command copy SRC into DEST, then hit the
            # venv-creation branch where the python3.11 missing
            # check fires.
            env = dict(os.environ)
            env["PATH"] = "/usr/bin:/bin"
            env["HOME"] = temp_home
            env.pop("AEGIS_DATA_DIR", None)

            result = subprocess.run(
                ["/bin/sh", str(out / "Install.command")],
                cwd=temp_home,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertNotEqual(
                result.returncode,
                0,
                f"Install.command should exit non-zero on missing "
                f"python3.11, got {result.returncode}; "
                f"stdout={result.stdout!r} stderr={result.stderr!r}",
            )
            combined = result.stdout + result.stderr
            self.assertIn(
                "python3.11 not found",
                combined,
                f"Install.command must print typed message; "
                f"got: {combined!r}",
            )
            self.assertIn(
                "3.11.9",
                combined,
                f"Install.command must name 3.11.9; got: {combined!r}",
            )
        finally:
            shutil.rmtree(temp_home, ignore_errors=True)

    # ------------------------------------------------------------------ #
    # 4) Install.command does not open Safari
    # ------------------------------------------------------------------ #
    def test_install_command_does_not_open_safari(self) -> None:
        """Install.command does not contain a Safari launch or
        an open -a call."""
        out = self._run_build()
        cmd_text = (out / "Install.command").read_text(encoding="utf-8")
        # Filter to non-comment code lines before checking for the
        # open command (echo instructions may legitimately say
        # 'open http://…').
        code_lines = [
            line
            for line in cmd_text.splitlines()
            if line.strip()
            and not line.strip().startswith("#")
        ]
        code_text = "\n".join(code_lines)
        self.assertNotRegex(
            code_text,
            r"(^|\n|\s)open\s+-a\b",
            "Install.command must not call open -a to launch a browser",
        )
        self.assertNotIn(
            "Safari",
            cmd_text,
            "Install.command must not mention Safari",
        )

    # ------------------------------------------------------------------ #
    # 5) No stripe token in core/
    # ------------------------------------------------------------------ #
    def test_no_stripe_token_in_core(self) -> None:
        """No .py file under core/ contains the token 'stripe'
        (case-insensitive)."""
        core_dir = REPO_ROOT / "core"
        if not core_dir.is_dir():
            self.skipTest("core/ directory not found")
        offenders = []
        for py in core_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="replace")
            if "stripe" in text.lower():
                offenders.append(str(py))
        self.assertEqual(
            offenders,
            [],
            f"core/ must not contain 'stripe' in any .py file: {offenders}",
        )

    # ------------------------------------------------------------------ #
    # 6) README Now names the double-click path, not notarized
    # ------------------------------------------------------------------ #
    def test_readme_now_names_double_click_path_not_notarized(
        self,
    ) -> None:
        """The README ## Now section names the double-click
        Install.command path and does not claim the installer is
        notarized."""
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        now_match = re.search(
            r"## Now\s*\n(.*?)(?=\n---\s*\n)",
            text,
            re.DOTALL,
        )
        assert now_match is not None, "README must have a Now section"
        now_section = now_match.group(1)
        self.assertIn(
            "Install.command",
            now_section,
            "README Now must name Install.command",
        )
        self.assertNotIn(
            "notarized",
            now_section.lower(),
            "README Now must not claim the installer is notarized",
        )


if __name__ == "__main__":
    unittest.main()
