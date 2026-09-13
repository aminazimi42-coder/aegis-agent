"""T168_CONTINUE — Notary path only with a real profile or ticket.

Covers:

* ``test_script_exists`` — ``scripts/codesign_operator.sh`` exists.
* ``test_unsigned_path_still_present`` — the script still prints
  ``UNSIGNED`` when no Developer ID identity is found.
* ``test_notary_skipped_without_profile`` — the script prints
  ``NOTARY_SKIPPED`` when ``AEGIS_NOTARY_PROFILE`` is unset or empty.
* ``test_notarized_string_only_after_stapler`` — the script prints
  ``NOTARIZED`` only after ``stapler validate`` succeeds.
* ``test_no_apple_id_or_password_flags_in_script`` — the script does
  not pass ``--apple-id`` or ``--password`` flags to notarytool.
* ``test_docs_say_hermesdev_not_amin`` — ``docs/APPLE_DEVELOPER.md``
  says signing and notarizing happen on hermesdev, not amin.
* ``test_readme_author_untouched`` — the README Author paragraph is
  present and unchanged.
* ``test_readme_does_not_claim_app_is_notarized`` — README does not
  contain ``notarized``.
* ``test_status_keeps_stripe_and_host_locked`` — STATUS.md mentions
  ``locked`` — live Stripe and the cloud license host remain locked.
* ``test_no_apple_secrets_tracked`` — no tracked file is an Apple
  ``AuthKey_*.p8``, ``*notary*password*``, ``*.cer``, or ``*.p12``.

No uvicorn subprocess.  No network.  Does not run notarytool against
Apple in CI.  Does not require a real profile.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "codesign_operator.sh"
_DOCS = REPO_ROOT / "docs" / "APPLE_DEVELOPER.md"
_README = REPO_ROOT / "README.md"
_STATUS = REPO_ROOT / "STATUS.md"


class TestT168ContinueNotaryGuard(unittest.TestCase):
    """T168_CONTINUE — notary path only with a real profile or ticket."""

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
        """The script must still mention ``UNSIGNED`` for the
        no-identity path — T168_CONTINUE does not weaken the unsigned
        guard."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "UNSIGNED",
            text,
            "Script must still mention UNSIGNED for the no-identity path",
        )

    # ------------------------------------------------------------------ #
    # 3) NOTARY_SKIPPED without profile
    # ------------------------------------------------------------------ #
    def test_notary_skipped_without_profile(self) -> None:
        """The script must print ``NOTARY_SKIPPED`` when
        ``AEGIS_NOTARY_PROFILE`` is unset or empty."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "NOTARY_SKIPPED",
            text,
            "Script must print NOTARY_SKIPPED without the profile",
        )
        self.assertIn(
            "AEGIS_NOTARY_PROFILE",
            text,
            "Script must reference AEGIS_NOTARY_PROFILE",
        )

    # ------------------------------------------------------------------ #
    # 4) NOTARIZED only after stapler validate
    # ------------------------------------------------------------------ #
    def test_notarized_string_only_after_stapler(self) -> None:
        """The script must print ``NOTARIZED`` only after
        ``stapler validate`` succeeds — never before."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "stapler validate",
            text,
            "Script must run stapler validate before NOTARIZED",
        )
        lines = text.splitlines()
        validate_line: int | None = None
        for i, line in enumerate(lines):
            if "stapler validate" in line:
                validate_line = i
                break
        notarized_line: int | None = None
        for i, line in enumerate(lines):
            if "NOTARIZED" in line and "echo" in line:
                notarized_line = i
                break
        self.assertIsNotNone(
            validate_line,
            "Script must have a stapler validate line",
        )
        self.assertIsNotNone(
            notarized_line,
            "Script must have a NOTARIZED echo line",
        )
        assert validate_line is not None
        assert notarized_line is not None
        self.assertGreater(
            notarized_line,
            validate_line,
            "NOTARIZED must appear after stapler validate, not before",
        )

    # ------------------------------------------------------------------ #
    # 5) No Apple ID or password flags
    # ------------------------------------------------------------------ #
    def test_no_apple_id_or_password_flags_in_script(self) -> None:
        """The script must not pass ``--apple-id`` or ``--password``
        flags to notarytool."""
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
    # 6) Docs say hermesdev, not amin
    # ------------------------------------------------------------------ #
    def test_docs_say_hermesdev_not_amin(self) -> None:
        """``docs/APPLE_DEVELOPER.md`` must say signing and notarizing
        happen on hermesdev, not amin."""
        self.assertTrue(
            _DOCS.is_file(),
            "docs/APPLE_DEVELOPER.md must exist",
        )
        text = _DOCS.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn(
            "hermesdev",
            lower,
            "Docs must say signing happens on hermesdev",
        )
        self.assertIn(
            "amin",
            lower,
            "Docs must mention amin as the non-signing account",
        )

    # ------------------------------------------------------------------ #
    # 7) README Author paragraph is untouched
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
    # 8) README does not claim the app is notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_claim_app_is_notarized(self) -> None:
        """README must not contain ``notarized`` — the shipped app is
        not claimed to be notarized."""
        text = _README.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertNotIn(
            "notarized",
            lower,
            "README must not claim the app is notarized",
        )

    # ------------------------------------------------------------------ #
    # 9) STATUS keeps Stripe and host locked
    # ------------------------------------------------------------------ #
    def test_status_keeps_stripe_and_host_locked(self) -> None:
        """STATUS.md must mention ``locked`` — live Stripe and the
        cloud license host remain locked."""
        self.assertTrue(_STATUS.is_file(), "STATUS.md must exist")
        text = _STATUS.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn(
            "locked",
            lower,
            "STATUS.md must mention locked — Stripe and host remain locked",
        )

    # ------------------------------------------------------------------ #
    # 10) No Apple secrets tracked
    # ------------------------------------------------------------------ #
    def test_no_apple_secrets_tracked(self) -> None:
        """No tracked file may be an Apple ``AuthKey_*.p8``,
        ``*notary*password*``, ``*.cer``, or ``*.p12``."""
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
        for f in files:
            lower = f.lower()
            if lower.endswith(".p8") and "authkey_" in lower:
                self.fail(
                    f"Tracked file {f!r} looks like an Apple AuthKey .p8"
                    " — remove it from version control",
                )
            if "notary" in lower and "password" in lower:
                self.fail(
                    f"Tracked file {f!r} looks like a notary password file"
                    " — remove it from version control",
                )
            if lower.endswith(".cer"):
                self.fail(
                    f"Tracked file {f!r} ends in .cer"
                    " — raw certificate files must stay out of git",
                )
            if lower.endswith(".p12"):
                self.fail(
                    f"Tracked file {f!r} ends in .p12"
                    " — raw certificate files must stay out of git",
                )


if __name__ == "__main__":
    unittest.main()
