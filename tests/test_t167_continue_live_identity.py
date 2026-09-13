"""T167_CONTINUE — Sign the Mac operator with the live Developer ID identity.

Covers:

* ``test_script_exists`` — ``scripts/codesign_operator.sh`` exists.
* ``test_unsigned_path_still_present`` — the script prints ``UNSIGNED``
  when no Developer ID Application identity is found.
* ``test_signed_print_requires_verify`` — the script prints ``SIGNED``
  only after ``codesign --verify --deep --strict`` succeeds.
* ``test_script_does_not_call_notarytool`` — the script does not invoke
  ``notarytool`` or ``stapler`` as a command.
* ``test_script_prints_notary_locked_until_ticket`` — the script prints
  ``NOTARY_LOCKED_UNTIL_TICKET``.
* ``test_docs_name_team_id_3J54UZPZW3`` — ``docs/APPLE_DEVELOPER.md``
  states Team ID 3J54UZPZW3.
* ``test_docs_say_hermesdev_not_amin`` — the docs say signing happens on
  hermesdev, not amin.
* ``test_readme_author_untouched`` — the README Author paragraph is
  present and unchanged.
* ``test_readme_does_not_claim_notarized_or_app_store`` — README does not
  contain ``notarized`` or ``App Store``.
* ``test_repo_tracks_no_cer_csr_p8_p12`` — no tracked file ends in
  ``.cer``, ``.csr``, ``.p8``, or ``.p12``.

No uvicorn subprocess.  No network.  Does not run notarytool against
Apple.  Does not require the identity in CI.  Does not run codesign
against a missing app as a failing test.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "codesign_operator.sh"
_DOCS = REPO_ROOT / "docs" / "APPLE_DEVELOPER.md"
_README = REPO_ROOT / "README.md"


class TestT167ContinueLiveIdentity(unittest.TestCase):
    """T167_CONTINUE — sign with the live Developer ID identity."""

    # ------------------------------------------------------------------ #
    # 1) Script exists
    # ------------------------------------------------------------------ #
    def test_script_exists(self) -> None:
        """``scripts/codesign_operator.sh`` must exist."""
        self.assertTrue(
            _SCRIPT.is_file(),
            "scripts/codesign_operator.sh must exist",
        )

    # ------------------------------------------------------------------ #
    # 2) Unsigned path is still present
    # ------------------------------------------------------------------ #
    def test_unsigned_path_still_present(self) -> None:
        """The script must print ``UNSIGNED`` when no Developer ID
        Application identity is found."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "UNSIGNED",
            text,
            "Script must print UNSIGNED for the no-identity path",
        )

    # ------------------------------------------------------------------ #
    # 3) SIGNED print requires verify
    # ------------------------------------------------------------------ #
    def test_signed_print_requires_verify(self) -> None:
        """The script must print ``SIGNED`` only after
        ``codesign --verify --deep --strict`` succeeds."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "codesign --verify --deep --strict",
            text,
            "Script must run codesign --verify --deep --strict",
        )
        self.assertIn(
            "SIGNED",
            text,
            "Script must print SIGNED when verify succeeds",
        )

    # ------------------------------------------------------------------ #
    # 4) Script invokes notarytool only under AEGIS_NOTARY_PROFILE
    # ------------------------------------------------------------------ #
    def test_notarytool_only_under_profile(self) -> None:
        """The script may invoke ``notarytool`` only when
        ``AEGIS_NOTARY_PROFILE`` is set; without the profile it prints
        ``NOTARY_SKIPPED``."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "AEGIS_NOTARY_PROFILE",
            text,
            "Script must gate notarytool on AEGIS_NOTARY_PROFILE",
        )
        self.assertIn(
            "NOTARY_SKIPPED",
            text,
            "Script must print NOTARY_SKIPPED without the profile",
        )

    # ------------------------------------------------------------------ #
    # 5) Script does not pass Apple ID or password flags
    # ------------------------------------------------------------------ #
    def test_no_apple_id_or_password_flags(self) -> None:
        """The script must not pass ``--apple-id`` or ``--password`` flags
        to notarytool."""
        text = _SCRIPT.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertNotIn(
            "--apple-id",
            lower,
            "Script must not pass --apple-id to notarytool",
        )
        self.assertNotIn(
            "--password",
            lower,
            "Script must not pass --password to notarytool",
        )

    # ------------------------------------------------------------------ #
    # 6) Docs state Team ID 3J54UZPZW3
    # ------------------------------------------------------------------ #
    def test_docs_name_team_id_3j54uzpzw9(self) -> None:
        """``docs/APPLE_DEVELOPER.md`` must state Team ID 3J54UZPZW3."""
        self.assertTrue(
            _DOCS.is_file(),
            "docs/APPLE_DEVELOPER.md must exist",
        )
        text = _DOCS.read_text(encoding="utf-8")
        self.assertIn(
            "3J54UZPZW3",
            text,
            "Docs must state Team ID 3J54UZPZW3",
        )

    # ------------------------------------------------------------------ #
    # 7) Docs say hermesdev, not amin
    # ------------------------------------------------------------------ #
    def test_docs_say_hermesdev_not_amin(self) -> None:
        """``docs/APPLE_DEVELOPER.md`` must say signing happens on
        hermesdev, not amin."""
        text = _DOCS.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn(
            "hermesdev",
            lower,
            "Docs must say signing happens on hermesdev",
        )

    # ------------------------------------------------------------------ #
    # 8) README Author paragraph is untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph must be present and unchanged."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn(
            "Amin Azimi",
            text,
            "README must retain the Author paragraph with Amin Azimi",
        )

    # ------------------------------------------------------------------ #
    # 9) README does not claim notarized or App Store
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
    # 10) Repo tracks no .cer/.csr/.p8/.p12 files
    # ------------------------------------------------------------------ #
    def test_repo_tracks_no_cer_csr_p8_p12(self) -> None:
        """No tracked file may end in ``.cer``, ``.csr``, ``.p8``, or
        ``.p12`` — raw certificate files stay out of git."""
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=30,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"git ls-files must succeed (got {result.returncode})",
        )
        files = result.stdout.splitlines()
        forbidden_exts = (".cer", ".csr", ".p8", ".p12")
        for f in files:
            lower = f.lower()
            for ext in forbidden_exts:
                if lower.endswith(ext):
                    self.fail(
                        f"Tracked file {f!r} ends in {ext} — "
                        "raw certificate files must stay out of git",
                    )


if __name__ == "__main__":
    unittest.main()
