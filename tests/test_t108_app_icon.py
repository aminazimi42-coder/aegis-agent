"""T108 — macOS app icon from local cover file.

Covers:
- ``desktop/macos/Aegis.app/Contents/Resources/AppIcon.png`` exists.
- ``Info.plist`` names ``AppIcon`` as the ``CFBundleIconFile`` value.
- No live network.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_BUNDLE = REPO_ROOT / "desktop" / "macos" / "Aegis.app"
PLIST_PATH = APP_BUNDLE / "Contents" / "Info.plist"
ICON_PNG_PATH = APP_BUNDLE / "Contents" / "Resources" / "AppIcon.png"


class TestT108AppIcon(unittest.TestCase):
    """Aegis.app shows a real icon, not the generic document tile."""

    def test_appicon_png_exists(self) -> None:
        """AppIcon.png exists inside the app bundle Resources folder."""
        self.assertTrue(
            ICON_PNG_PATH.is_file(),
            f"Expected {ICON_PNG_PATH} to exist",
        )

    def test_plist_names_appicon(self) -> None:
        """Info.plist CFBundleIconFile value is ``AppIcon``."""
        text = PLIST_PATH.read_text(encoding="utf-8")
        self.assertIn("<key>CFBundleIconFile</key>", text)
        self.assertIn("<string>AppIcon</string>", text)

    def test_no_live_network(self) -> None:
        """This module does not import urllib/requests/socket/http."""
        import ast
        import inspect
        import sys

        tree = ast.parse(inspect.getsource(sys.modules[__name__]))
        banned = {"urllib", "requests", "socket", "http.client"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in banned:
                        self.fail(f"{__name__} imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in banned or mod.startswith("urllib."):
                    self.fail(f"{__name__} imports from '{mod}'")


if __name__ == "__main__":
    unittest.main()
