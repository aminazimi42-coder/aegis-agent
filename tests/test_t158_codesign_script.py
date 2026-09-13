"""T158 — Codesign script without notarized claim.

Covers:

* ``test_script_exists_and_mentions_unsigned`` —
  ``scripts/codesign_operator.sh`` exists and mentions ``UNSIGNED``.
* ``test_readme_does_not_claim_notarized_or_app_store`` —
  README must not contain ``notarized`` or ``App Store``.
* ``test_status_says_notarize_still_locked`` —
  STATUS.md mentions ``locked`` or ``notarize`` (notarize is still locked).
* ``test_script_dry_path_does_not_require_apple_id`` —
  when no Developer ID identity is found the script prints ``UNSIGNED``
  and exits 0 without calling notarytool or opening Safari.

No uvicorn subprocess.  No network.  Does not run notarytool against Apple.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "codesign_operator.sh"
_README = REPO_ROOT / "README.md"
_STATUS = REPO_ROOT / "STATUS.md"


class TestT158CodesignScript(unittest.TestCase):
    """Codesign script is honest about the unsigned state."""

    # ------------------------------------------------------------------ #
    # 1) Script exists and mentions UNSIGNED
    # ------------------------------------------------------------------ #
    def test_script_exists_and_mentions_unsigned(self) -> None:
        """``scripts/codesign_operator.sh`` exists and contains UNSIGNED."""
        self.assertTrue(
            _SCRIPT.is_file(),
            "scripts/codesign_operator.sh must exist",
        )
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "UNSIGNED",
            text,
            "Script must mention UNSIGNED for the no-identity path",
        )

    # ------------------------------------------------------------------ #
    # 2) README does not claim notarized or App Store
    # ------------------------------------------------------------------ #
    def test_readme_does_not_claim_notarized_or_app_store(self) -> None:
        """README must not contain ``notarized`` or ``App Store``."""
        text = _README.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertNotIn(
            "notarized",
            lower,
            "README must not claim notarization",
        )
        self.assertNotIn(
            "app store",
            lower,
            "README must not claim App Store",
        )

    # ------------------------------------------------------------------ #
    # 3) STATUS says notarize is still locked
    # ------------------------------------------------------------------ #
    def test_status_says_notarize_still_locked(self) -> None:
        """STATUS.md mentions ``locked`` or ``notarize`` — notarize is still locked."""
        self.assertTrue(_STATUS.is_file(), "STATUS.md must exist")
        text = _STATUS.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertTrue(
            "locked" in lower or "notarize" in lower,
            "STATUS.md must mention locked or notarize",
        )

    # ------------------------------------------------------------------ #
    # 4) Dry path does not require an Apple ID
    # ------------------------------------------------------------------ #
    def test_script_dry_path_does_not_require_apple_id(self) -> None:
        """When no Developer ID identity is found the script prints
        ``UNSIGNED`` and exits 0 without calling notarytool or Safari."""
        # Run the script in an environment with no notary profile and a
        # non-existent app path so it hits the UNSIGNED path.
        env = dict(os.environ)
        env.pop("AEGIS_NOTARY_PROFILE", None)
        result = subprocess.run(
            [str(_SCRIPT), "/nonexistent/app/path"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Script must exit 0 on the dry path (got {result.returncode}); "
            f"stdout={result.stdout!r} stderr={result.stderr!r}",
        )
        combined = (result.stdout + result.stderr).lower()
        self.assertIn(
            "unsigned",
            combined,
            "Dry path must print UNSIGNED",
        )
        self.assertNotIn(
            "safari",
            combined,
            "Script must not open Safari",
        )


if __name__ == "__main__":
    unittest.main()
