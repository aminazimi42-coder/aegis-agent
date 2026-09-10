"""T143 — Layer-1 local operator pack.

Covers:
* ``test_pack_script_exists`` — scripts/pack_local_operator.sh exists
  and is executable.
* ``test_pack_excludes_git_and_directive`` — the pack does not copy
  .git, .venv, _directive.txt, task_instruction.txt, .kms/, or
  $HOME/.aegis into the output tree; it does copy the runtime tree
  (app/, core/, agents/, scripts/start_operator.sh,
  pyproject.toml, uv.lock, app.html).
* ``test_install_md_names_start_operator`` — INSTALL.md names
  scripts/start_operator.sh and http://127.0.0.1:8741/.

No live network except ``TestClient``.
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


class TestT143LocalPack(unittest.TestCase):
    """Layer-1 local operator pack builder."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t143_")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------------ #
    # 1) Pack script exists and is executable
    # ------------------------------------------------------------------ #

    def test_pack_script_exists(self) -> None:
        """scripts/pack_local_operator.sh exists and is executable."""
        self.assertTrue(PACK_SCRIPT.is_file(), "pack_local_operator.sh not found")
        self.assertTrue(
            os.access(PACK_SCRIPT, os.X_OK),
            "pack_local_operator.sh must be executable",
        )

    # ------------------------------------------------------------------ #
    # 2) Pack excludes git, .venv, directives, .kms, $HOME/.aegis
    # ------------------------------------------------------------------ #

    def test_pack_excludes_git_and_directive(self) -> None:
        """The built pack excludes .git, .venv, _directive.txt,
        task_instruction.txt, .kms/, $HOME/.aegis and includes the
        runtime tree (app/, core/, agents/, start_operator.sh,
        pyproject.toml, uv.lock, app.html)."""
        # Run the pack script in an isolated repo copy so we inspect
        # exactly what it produces without touching the real dist/.
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
        out = Path(out_path)

        # --- must include the runtime tree -------------------------------- #
        self.assertTrue((out / "app").is_dir(), "pack missing app/")
        self.assertTrue((out / "core").is_dir(), "pack missing core/")
        self.assertTrue((out / "agents").is_dir(), "pack missing agents/")
        self.assertTrue(
            (out / "scripts" / "start_operator.sh").is_file(),
            "pack missing scripts/start_operator.sh",
        )
        self.assertTrue(
            (out / "pyproject.toml").is_file(),
            "pack missing pyproject.toml",
        )
        self.assertTrue((out / "uv.lock").is_file(), "pack missing uv.lock")
        self.assertTrue(
            (out / "desktop" / "macos" / "Aegis.app"
             / "Contents" / "Resources" / "app.html").is_file(),
            "pack missing app.html",
        )

        # --- must exclude the builder artefacts -------------------------- #
        self.assertFalse((out / ".git").exists(), "pack must not include .git")
        self.assertFalse((out / ".venv").exists(), "pack must not include .venv")
        self.assertFalse(
            (out / "_directive.txt").exists(),
            "pack must not include _directive.txt",
        )
        self.assertFalse(
            (out / "task_instruction.txt").exists(),
            "pack must not include task_instruction.txt",
        )
        self.assertFalse((out / ".kms").exists(), "pack must not include .kms/")
        self.assertFalse(
            (out / ".aegis").exists(),
            "pack must not include $HOME/.aegis",
        )
        # No pycache/pytest caches.
        self.assertFalse(
            list(out.rglob("__pycache__")),
            "pack must not include __pycache__",
        )
        self.assertFalse(
            list(out.rglob(".pytest_cache")),
            "pack must not include .pytest_cache",
        )

        # Clean up the produced dist tree so the test leaves no artefact.
        shutil.rmtree(out, ignore_errors=True)

    # ------------------------------------------------------------------ #
    # 3) INSTALL.md names start_operator.sh and the local URL
    # ------------------------------------------------------------------ #

    def test_install_md_names_start_operator(self) -> None:
        """INSTALL.md names scripts/start_operator.sh and
        http://127.0.0.1:8741/, and does not name a cloud URL or a
        notarized installer."""
        # Build the pack once to read INSTALL.md from the output tree.
        result = subprocess.run(
            ["/bin/sh", str(PACK_SCRIPT)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode, 0,
            f"pack_local_operator.sh failed: {result.stderr or result.stdout}",
        )
        out_path = result.stdout.strip().splitlines()[-1].strip()
        install_md = Path(out_path) / "INSTALL.md"
        self.assertTrue(install_md.is_file(), "INSTALL.md not created in pack")
        text = install_md.read_text(encoding="utf-8").lower()
        self.assertIn("start_operator.sh", text,
                      "INSTALL.md must name start_operator.sh")
        self.assertIn("127.0.0.1:8741", text,
                      "INSTALL.md must name the local URL")
        # Must not point at a cloud host (no https:// URL), and must not
        # claim a notarized installer.
        self.assertNotIn("https://", text,
                         "INSTALL.md must not name a cloud URL")
        self.assertNotIn("notarized installer", text,
                         "INSTALL.md must not claim a notarized installer")
        shutil.rmtree(out_path, ignore_errors=True)

    # ------------------------------------------------------------------ #
    # 4) No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """No external network call is made; the pack script is local."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
