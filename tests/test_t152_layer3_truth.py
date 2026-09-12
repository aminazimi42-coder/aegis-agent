"""T152 — Honest Layer 3 Now vs Planned.

Covers:

* ``test_readme_names_unsigned_installer`` — README names the unsigned
  installer (``AegisOperator-mac`` or ``build_mac_installer``) and says
  ``unsigned``.
* ``test_readme_does_not_claim_notarized_or_app_store`` — README does not
  contain the word ``notarized`` (case-insensitive) and does not contain
  ``App Store``.
* ``test_readme_does_not_claim_license_server_deployed`` — README does
  not claim a deployed license server (no ``license server deployed``
  or ``license host live`` phrase).
* ``test_status_says_trial_not_yet_recorded`` — STATUS.md says the
  installer laptop trial is not yet recorded (``trial`` and
  ``not yet``).

No uvicorn subprocess.  No network.  Text-only assertions on repo files.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_README = REPO_ROOT / "README.md"
_STATUS = REPO_ROOT / "STATUS.md"


class TestT152Layer3Truth(unittest.TestCase):
    """Honest Layer 3 Now vs Planned in README and STATUS."""

    # ------------------------------------------------------------------ #
    # 1) README names the unsigned installer
    # ------------------------------------------------------------------ #
    def test_readme_names_unsigned_installer(self) -> None:
        """README names ``AegisOperator-mac`` or ``build_mac_installer``
        and says ``unsigned``."""
        text = _README.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertTrue(
            "aegisoperator-mac" in lower or "build_mac_installer" in lower,
            "README must name the unsigned installer",
        )
        self.assertIn(
            "unsigned",
            lower,
            "README must say unsigned for the Layer-3 installer",
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
    # 3) README does not claim a deployed license server
    # ------------------------------------------------------------------ #
    def test_readme_does_not_claim_license_server_deployed(self) -> None:
        """README must not claim a deployed or live license server."""
        text = _README.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertNotIn(
            "license server deployed",
            lower,
            "README must not claim a deployed license server",
        )
        self.assertNotIn(
            "license host live",
            lower,
            "README must not claim a live license host",
        )
        self.assertNotIn(
            "license server is live",
            lower,
            "README must not claim a live license server",
        )

    # ------------------------------------------------------------------ #
    # 4) STATUS says trial not yet recorded
    # ------------------------------------------------------------------ #
    def test_status_says_trial_not_yet_recorded(self) -> None:
        """STATUS.md says the installer laptop trial is not yet
        recorded."""
        self.assertTrue(
            _STATUS.is_file(),
            "STATUS.md must exist",
        )
        text = _STATUS.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn(
            "trial",
            lower,
            "STATUS.md must mention the installer trial",
        )
        self.assertIn(
            "not yet",
            lower,
            "STATUS.md must say the trial is not yet recorded",
        )


if __name__ == "__main__":
    unittest.main()
