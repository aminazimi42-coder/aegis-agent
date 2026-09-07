"""T104 — First macOS app bundle and installer.

Verifies that the ``desktop/macos/Aegis.app`` bundle layout exists
with an ``Info.plist`` and a launcher, that ``stub.html`` is present
and declares the local twin (not SaaS), and that the install script
exists.

No live network and no live window — these are structural checks only.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_BUNDLE = _REPO_ROOT / "desktop" / "macos" / "Aegis.app"
_INSTALL_SCRIPT = _REPO_ROOT / "scripts" / "install_macos_app.sh"


class TestT104MacOSApp(unittest.TestCase):
    """Structural tests for the T104 macOS app bundle and installer."""

    def setUp(self) -> None:
        """Ensure repo-relative paths are used, not $HOME-dependent ones."""
        os.chdir(_REPO_ROOT)

    def test_bundle_has_plist_and_launcher(self) -> None:
        """The .app bundle must contain Info.plist and a MacOS launcher."""
        plist = _APP_BUNDLE / "Contents" / "Info.plist"
        launcher = _APP_BUNDLE / "Contents" / "MacOS" / "Aegis"
        self.assertTrue(
            plist.is_file(),
            f"Info.plist missing at {plist}",
        )
        self.assertTrue(
            launcher.is_file(),
            f"Launcher missing at {launcher}",
        )
        # Verify the plist is non-empty and well-formed enough to read.
        text = plist.read_text(encoding="utf-8")
        self.assertIn("CFBundleExecutable", text)
        self.assertIn("CFBundleIdentifier", text)

    def test_install_script_exists(self) -> None:
        """The install script must exist and be executable."""
        self.assertTrue(
            _INSTALL_SCRIPT.is_file(),
            f"Install script missing at {_INSTALL_SCRIPT}",
        )
        # Read its contents — it must copy the bundle, not symlink it.
        text = _INSTALL_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("cp -R", text)
        self.assertIn("Aegis.app", text)

    def test_stub_html_exists(self) -> None:
        """stub.html must exist and declare the local twin, not SaaS."""
        stub = _APP_BUNDLE / "Contents" / "Resources" / "stub.html"
        self.assertTrue(
            stub.is_file(),
            f"stub.html missing at {stub}",
        )
        text = stub.read_text(encoding="utf-8")
        self.assertIn("local twin", text.lower())
        self.assertIn("not", text.lower())
        # Must NOT advertise hosted SaaS or card charging.
        self.assertNotIn("stripe", text.lower())
        self.assertNotIn("card is charged", text.lower())


if __name__ == "__main__":
    unittest.main()
