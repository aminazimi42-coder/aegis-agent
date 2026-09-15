"""T184 — Notary staple-only helper, conditions the success word on
``stapler validate`` exiting 0.

Covers:

* ``test_script_exists`` — ``scripts/notarize_staple.sh`` exists and is
  executable.
* ``test_script_no_submit_zip`` — the staple script does not build a
  zip with ``ditto`` and does not call ``notarytool submit`` —
  submission stays in T183.
* ``test_script_conditions_notarized_on_stapler_validate`` — the
  script runs ``stapler staple`` then ``stapler validate`` and prints
  ``NOTARIZED`` only if ``stapler validate`` exits 0.
* ``test_script_profile_missing_path`` — without
  ``AEGIS_NOTARY_PROFILE`` the script prints ``NOTARY_PROFILE_MISSING``
  and exits 0.
* ``test_readme_does_not_claim_app_is_notarized`` — README does not
  contain ``notarized``.
* ``test_no_apple_secrets_tracked`` — no tracked file is an Apple
  ``AuthKey_*.p8``, ``*notary*password*``, ``*.cer``, or ``*.p12``.

No uvicorn subprocess.  No network.  Does not call notarytool against
Apple in pytest.  Does not start uvicorn.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "notarize_staple.sh"
_README = REPO_ROOT / "README.md"


class TestT184NotaryStaple(unittest.TestCase):
    """T184 — notary staple helper only after Accepted."""

    # ------------------------------------------------------------------ #
    # 1) Script exists
    # ------------------------------------------------------------------ #
    def test_script_exists(self) -> None:
        """``scripts/notarize_staple.sh`` must exist and be executable."""
        self.assertTrue(
            _SCRIPT.is_file(),
            "scripts/notarize_staple.sh must exist",
        )
        self.assertTrue(
            _SCRIPT.stat().st_mode & 0o100,
            "scripts/notarize_staple.sh must be executable",
        )

    # ------------------------------------------------------------------ #
    # 2) No submit or zip — submission stays in T183
    # ------------------------------------------------------------------ #
    def test_script_no_submit_zip(self) -> None:
        """The staple script must not call ``notarytool submit`` or build
        a zip with ``ditto`` — submission stays in T183."""
        text = _SCRIPT.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertNotIn(
            "notarytool submit",
            lower,
            "Staple script must not call notarytool submit — "
            "submission stays in T183",
        )
        self.assertNotIn(
            "ditto",
            lower,
            "Staple script must not build a zip with ditto — "
            "that is T183's job",
        )

    # ------------------------------------------------------------------ #
    # 3) NOTARIZED only after stapler validate exits 0
    # ------------------------------------------------------------------ #
    def test_script_conditions_notarized_on_stapler_validate(self) -> None:
        """The script must run ``stapler staple`` then
        ``stapler validate`` and print ``NOTARIZED`` only if
        ``stapler validate`` exits 0."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "stapler staple",
            text,
            "Script must run stapler staple",
        )
        self.assertIn(
            "stapler validate",
            text,
            "Script must run stapler validate",
        )
        # NOTARIZED must appear after stapler validate, not before.
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
    # 4) Profile-missing path — NOTARY_PROFILE_MISSING and exit 0
    # ------------------------------------------------------------------ #
    def test_script_profile_missing_path(self) -> None:
        """Without ``AEGIS_NOTARY_PROFILE`` the script must print
        ``NOTARY_PROFILE_MISSING`` and exit 0 (not fail CI)."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "NOTARY_PROFILE_MISSING",
            text,
            "Script must print NOTARY_PROFILE_MISSING when profile is absent",
        )
        # The profile-missing branch must exit 0, not exit 1.
        # Search for the echo line, not the comment mention.
        lines = text.splitlines()
        in_profile_missing = False
        found_exit_0 = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('echo "NOTARY_PROFILE_MISSING"'):
                in_profile_missing = True
                continue
            if in_profile_missing:
                if stripped.startswith("exit 0"):
                    found_exit_0 = True
                    break
                if stripped.startswith("exit 1") or stripped.startswith(
                    "exit 2",
                ):
                    self.fail(
                        "Profile-missing branch must exit 0, not "
                        f"{stripped}",
                    )
        self.assertTrue(
            found_exit_0,
            "Profile-missing branch must contain 'exit 0'",
        )
        # Also check the store-credentials command is referenced.
        self.assertIn(
            "store-credentials",
            text,
            "Script must reference the store-credentials owner command",
        )

    # ------------------------------------------------------------------ #
    # 5) README does not claim the app is notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_claim_app_is_notarized(self) -> None:
        """README must not contain ``notarized`` — the shipped app is
        not claimed to be notarized unless stapler validate has run."""
        text = _README.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertNotIn(
            "notarized",
            lower,
            "README must not claim the app is notarized",
        )

    # ------------------------------------------------------------------ #
    # 6) No Apple secrets tracked
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
