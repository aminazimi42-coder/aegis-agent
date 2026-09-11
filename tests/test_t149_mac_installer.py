"""T149 — Mac installer folder separate from the repo.

Covers:

* ``test_build_script_exists_and_executable`` —
  ``scripts/build_mac_installer.sh`` exists and is executable.
* ``test_installer_folder_contains_pack_and_install_command`` — after
  running the build script, ``dist/AegisOperator-mac/`` contains
  ``aegis-local-operator/`` (with ``start_operator.sh``) and
  ``Install.command``.
* ``test_app_bundle_has_plist_and_macos_stub`` — the ``Aegis
  Operator.app`` bundle has ``Contents/Info.plist`` (with
  ``CFBundleName`` = ``Aegis Operator`` and ``CFBundleIdentifier`` =
  ``lab.azimi.aegis.operator``) and ``Contents/MacOS/AegisOperator``.
* ``test_installer_omits_git_directive_and_live_aegis`` — the installer
  folder has no ``.git``, no ``_directive.txt``, no
  ``task_instruction.txt``, no ``.kms``, and no live ``.aegis``.
* ``test_install_md_says_unsigned_and_does_not_open_safari`` —
  ``INSTALL.md`` says the app is unsigned and does not tell the user to
  open a browser via a script.
* ``test_readme_names_aegisoperator_mac`` — the repo README names
  ``dist/AegisOperator-mac`` and ``scripts/build_mac_installer.sh``.

No uvicorn subprocess.  No ``Install.command`` run against the builder
home.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_mac_installer.sh"


class TestT149MacInstaller(unittest.TestCase):
    """Mac installer folder is built by scripts/build_mac_installer.sh."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t149_")
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
    # 1) Build script exists and is executable
    # ------------------------------------------------------------------ #
    def test_build_script_exists_and_executable(self) -> None:
        """scripts/build_mac_installer.sh exists and is executable."""
        self.assertTrue(
            BUILD_SCRIPT.is_file(),
            "build_mac_installer.sh not found",
        )
        self.assertTrue(
            os.access(BUILD_SCRIPT, os.X_OK),
            "build_mac_installer.sh must be executable",
        )

    # ------------------------------------------------------------------ #
    # 2) Installer folder contains the pack and Install.command
    # ------------------------------------------------------------------ #
    def test_installer_folder_contains_pack_and_install_command(
        self,
    ) -> None:
        """The installer folder contains aegis-local-operator/ (with
        start_operator.sh) and Install.command."""
        out = self._run_build()
        self.assertTrue(
            (out / "aegis-local-operator").is_dir(),
            "installer folder missing aegis-local-operator/",
        )
        self.assertTrue(
            (out / "aegis-local-operator" / "start_operator.sh").is_file(),
            "installer pack missing start_operator.sh",
        )
        self.assertTrue(
            (out / "Install.command").is_file(),
            "installer folder missing Install.command",
        )

    # ------------------------------------------------------------------ #
    # 3) App bundle has plist and MacOS stub
    # ------------------------------------------------------------------ #
    def test_app_bundle_has_plist_and_macos_stub(self) -> None:
        """The Aegis Operator.app bundle has Info.plist with the correct
        CFBundleName and CFBundleIdentifier, and a MacOS/AegisOperator
        executable stub."""
        out = self._run_build()
        app = out / "Aegis Operator.app"
        self.assertTrue(app.is_dir(), "Aegis Operator.app missing")
        plist = app / "Contents" / "Info.plist"
        self.assertTrue(plist.is_file(), "Info.plist missing")
        plist_text = plist.read_text(encoding="utf-8")
        self.assertIn("Aegis Operator", plist_text)
        self.assertIn("lab.azimi.aegis.operator", plist_text)
        stub = app / "Contents" / "MacOS" / "AegisOperator"
        self.assertTrue(stub.is_file(), "MacOS/AegisOperator stub missing")
        self.assertTrue(
            os.access(stub, os.X_OK),
            "AegisOperator stub must be executable",
        )

    # ------------------------------------------------------------------ #
    # 4) Installer omits git, directive, and live .aegis
    # ------------------------------------------------------------------ #
    def test_installer_omits_git_directive_and_live_aegis(self) -> None:
        """The installer folder has no .git, no _directive.txt, no
        task_instruction.txt, no .kms, and no live .aegis."""
        out = self._run_build()
        self.assertFalse(
            (out / ".git").exists(),
            "installer must not include .git",
        )
        self.assertFalse(
            (out / "_directive.txt").exists(),
            "installer must not include _directive.txt",
        )
        self.assertFalse(
            (out / "task_instruction.txt").exists(),
            "installer must not include task_instruction.txt",
        )
        self.assertFalse(
            (out / ".kms").exists(),
            "installer must not include .kms/",
        )
        self.assertFalse(
            (out / ".aegis").exists(),
            "installer must not include a live .aegis/",
        )

    # ------------------------------------------------------------------ #
    # 5) INSTALL.md says unsigned and does not open Safari
    # ------------------------------------------------------------------ #
    def test_install_md_says_unsigned_and_does_not_open_safari(
        self,
    ) -> None:
        """INSTALL.md says the app is unsigned, and Install.command
        does not contain a browser-launch command (no ``open`` call)."""
        out = self._run_build()
        text = (out / "INSTALL.md").read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn("unsigned", lower, "INSTALL.md must say unsigned")
        self.assertIn("notarized", lower, "INSTALL.md must reference notarized")
        # Install.command must not open a browser.
        cmd_text = (out / "Install.command").read_text(encoding="utf-8")
        cmd_lower = cmd_text.lower()
        self.assertNotIn(
            "open ",
            cmd_lower,
            "Install.command must not open a browser",
        )

    # ------------------------------------------------------------------ #
    # 6) README names dist/AegisOperator-mac
    # ------------------------------------------------------------------ #
    def test_readme_names_aegisoperator_mac(self) -> None:
        """The repo README names dist/AegisOperator-mac and
        scripts/build_mac_installer.sh."""
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "AegisOperator-mac",
            text,
            "README must name dist/AegisOperator-mac",
        )
        self.assertIn(
            "build_mac_installer.sh",
            text,
            "README must name scripts/build_mac_installer.sh",
        )


if __name__ == "__main__":
    unittest.main()
