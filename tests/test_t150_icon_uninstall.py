"""T150 — App icon resource and data-preserving uninstall.

Covers:

* ``test_app_bundle_has_icon_resource`` — after running the build script,
  ``Aegis Operator.app/Contents/Resources/AppIcon.png`` exists and is a
  valid PNG (starts with the PNG signature).
* ``test_plist_names_icon`` — ``Info.plist`` contains ``CFBundleIconFile``
  referencing ``AppIcon.png``.
* ``test_uninstall_script_exists_and_executable`` —
  ``scripts/uninstall_aegis_operator.sh`` exists and is executable.
* ``test_uninstall_script_does_not_delete_aegis_data_dir`` — the uninstall
  script does not contain ``rm`` targeting ``$HOME/.aegis`` or any path
  under it.
* ``test_install_md_says_uninstall_keeps_data`` — ``INSTALL.md`` in the
  installer folder says uninstall removes the program folder and does not
  delete ``$HOME/.aegis``.

No uvicorn subprocess.  No uninstall run against the builder home.
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
UNINSTALL_SCRIPT = REPO_ROOT / "scripts" / "uninstall_aegis_operator.sh"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class TestT150IconUninstall(unittest.TestCase):
    """App icon and data-preserving uninstall for the Mac installer."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t150_")
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
    # 1) App bundle has an icon resource
    # ------------------------------------------------------------------ #
    def test_app_bundle_has_icon_resource(self) -> None:
        """Aegis Operator.app/Contents/Resources/AppIcon.png exists and
        is a valid PNG."""
        out = self._run_build()
        icon = (
            out
            / "Aegis Operator.app"
            / "Contents"
            / "Resources"
            / "AppIcon.png"
        )
        self.assertTrue(icon.is_file(), "AppIcon.png missing from app bundle")
        data = icon.read_bytes()
        self.assertTrue(
            data.startswith(PNG_SIGNATURE),
            "AppIcon.png is not a valid PNG",
        )
        self.assertGreater(len(data), 100, "AppIcon.png is suspiciously small")

    # ------------------------------------------------------------------ #
    # 2) Info.plist names the icon
    # ------------------------------------------------------------------ #
    def test_plist_names_icon(self) -> None:
        """Info.plist contains CFBundleIconFile referencing AppIcon.png."""
        out = self._run_build()
        plist = (
            out
            / "Aegis Operator.app"
            / "Contents"
            / "Info.plist"
        )
        text = plist.read_text(encoding="utf-8")
        self.assertIn("CFBundleIconFile", text, "plist missing CFBundleIconFile")
        self.assertIn("AppIcon.png", text, "plist CFBundleIconFile must name AppIcon.png")

    # ------------------------------------------------------------------ #
    # 3) Uninstall script exists and is executable
    # ------------------------------------------------------------------ #
    def test_uninstall_script_exists_and_executable(self) -> None:
        """scripts/uninstall_aegis_operator.sh exists and is executable."""
        self.assertTrue(
            UNINSTALL_SCRIPT.is_file(),
            "uninstall_aegis_operator.sh not found",
        )
        self.assertTrue(
            os.access(UNINSTALL_SCRIPT, os.X_OK),
            "uninstall_aegis_operator.sh must be executable",
        )

    # ------------------------------------------------------------------ #
    # 4) Uninstall script does not delete $HOME/.aegis
    # ------------------------------------------------------------------ #
    def test_uninstall_script_does_not_delete_aegis_data_dir(self) -> None:
        """The uninstall script must not rm $HOME/.aegis or anything
        under it, must not touch the git repo or /Users/Shared, and
        must not kill port 8741 or open a browser."""
        text = UNINSTALL_SCRIPT.read_text(encoding="utf-8")
        lower = text.lower()
        # Must remove $HOME/aegis-local-operator
        self.assertIn(
            "aegis-local-operator",
            lower,
            "uninstall must target aegis-local-operator",
        )
        # Must NOT rm the data dir
        self.assertNotIn(
            "rm -rf \"$HOME/.aegis\"",
            text,
            "uninstall must not rm $HOME/.aegis",
        )
        self.assertNotIn(
            "rm -rf \"$HOME/.aegis/\"",
            text,
            "uninstall must not rm $HOME/.aegis/",
        )
        # Non-comment lines only — comments may mention paths/commands
        # that the script itself does not execute.
        code_lines = [
            line
            for line in text.splitlines()
            if line.strip()
            and not line.strip().startswith("#")
        ]
        code_text = "\n".join(code_lines).lower()
        # Must not touch git repo or Shared in actual code.
        self.assertNotIn(
            "/users/hermesdev/aegis agent",
            code_text,
            "uninstall must not touch the git repo",
        )
        self.assertNotIn(
            "/users/shared",
            code_text,
            "uninstall must not touch /Users/Shared",
        )
        # Must not kill a process or open a browser in actual code.
        self.assertNotIn(
            "kill",
            code_text,
            "uninstall must not kill any process",
        )
        self.assertNotIn(
            "open ",
            code_text,
            "uninstall must not open a browser",
        )

    # ------------------------------------------------------------------ #
    # 5) INSTALL.md says uninstall keeps data
    # ------------------------------------------------------------------ #
    def test_install_md_says_uninstall_keeps_data(self) -> None:
        """INSTALL.md says uninstall removes the program folder and does
        not delete $HOME/.aegis."""
        out = self._run_build()
        text = (out / "INSTALL.md").read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn(
            "uninstall",
            lower,
            "INSTALL.md must mention uninstall",
        )
        self.assertIn(
            "$home/aegis-local-operator",
            lower,
            "INSTALL.md must name the program folder in uninstall context",
        )
        self.assertIn(
            "does not delete",
            lower,
            "INSTALL.md must say it does not delete $HOME/.aegis",
        )
        self.assertIn(
            "$home/.aegis",
            lower,
            "INSTALL.md must reference $HOME/.aegis in uninstall context",
        )
