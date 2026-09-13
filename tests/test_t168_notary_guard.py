"""T168 — Notary guard: notarytool only with a real ticket.

Covers:

* ``test_script_exists`` — ``scripts/codesign_operator.sh`` exists.
* ``test_unsigned_path_still_present`` — the script still prints
  ``UNSIGNED`` when no Developer ID identity is found.
* ``test_notary_skipped_without_profile`` — the script source prints
  ``NOTARY_SKIPPED`` when ``AEGIS_NOTARY_PROFILE`` is unset or empty.
* ``test_notarized_string_only_after_stapler`` — the script source
  conditions ``NOTARIZED`` on ``stapler validate`` succeeding, not on
  mere submission.
* ``test_readme_does_not_claim_app_is_notarized`` — README does not
  contain ``notarized``.
* ``test_status_keeps_stripe_and_host_locked`` — STATUS.md mentions
  ``locked``.
* ``test_no_apple_secrets_tracked`` — no ``AuthKey_*.p8`` or
  ``*notary*password*`` file is tracked.

No uvicorn subprocess.  No network.  Does not run notarytool against
Apple.  Does not require a real certificate in CI.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "codesign_operator.sh"
_README = REPO_ROOT / "README.md"
_STATUS = REPO_ROOT / "STATUS.md"


class TestT168NotaryGuard(unittest.TestCase):
    """T168 — notarytool path without a notarized lie."""

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
        """The script must still mention ``UNSIGNED`` for the no-identity
        path — T168 does not weaken the T167/T158 unsigned guard."""
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
        """The script source must print ``NOTARY_SKIPPED`` when
        ``AEGIS_NOTARY_PROFILE`` is unset or empty — and the
        ``NOTARY_LOCKED_UNTIL_T168`` marker must be gone."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "NOTARY_SKIPPED",
            text,
            "Script must print NOTARY_SKIPPED when no notary profile is set",
        )
        self.assertNotIn(
            "NOTARY_LOCKED_UNTIL_T168",
            text,
            "Script must not contain NOTARY_LOCKED_UNTIL_T168 after T168",
        )

    # ------------------------------------------------------------------ #
    # 4) NOTARIZED only after stapler validate
    # ------------------------------------------------------------------ #
    def test_notarized_string_only_after_stapler(self) -> None:
        """The script must condition ``NOTARIZED`` on
        ``stapler validate`` succeeding — not on mere submission."""
        text = _SCRIPT.read_text(encoding="utf-8")
        # The NOTARIZED echo must appear only inside the branch that
        # checks stapler validate, not before the submit call.
        self.assertIn(
            "stapler validate",
            text,
            "Script must call stapler validate",
        )
        # Find the NOTARIZED echo and confirm it is in the same block
        # as stapler validate, not in the submit block.
        lines = text.splitlines()
        notarized_line: int | None = None
        for i, line in enumerate(lines):
            if "NOTARIZED" in line and "echo" in line:
                notarized_line = i
                break
        self.assertIsNotNone(
            notarized_line,
            "Script must have an echo NOTARIZED line",
        )
        # Check that the NOTARIZED line appears after stapler validate,
        # not before the notarytool submit.
        validate_line: int | None = None
        for i, line in enumerate(lines):
            if "stapler validate" in line:
                validate_line = i
                break
        self.assertIsNotNone(
            validate_line,
            "Script must have a stapler validate line",
        )
        assert notarized_line is not None
        assert validate_line is not None
        self.assertGreater(
            notarized_line,
            validate_line,
            "NOTARIZED must appear after stapler validate, not before submit",
        )
        # Also confirm the NOTARIZED line is inside a conditional that
        # checks the validate exit code (the ``if stapler validate`` line
        # must come before the echo NOTARIZED line).
        block_start: int | None = None
        for i in range(notarized_line - 1, -1, -1):
            if "if stapler validate" in lines[i]:
                block_start = i
                break
        self.assertIsNotNone(
            block_start,
            "NOTARIZED must be inside an if-stapler-validate block",
        )

    # ------------------------------------------------------------------ #
    # 5) README does not claim the app is notarized
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
    # 6) STATUS keeps Stripe and host locked
    # ------------------------------------------------------------------ #
    def test_status_keeps_stripe_and_host_locked(self) -> None:
        """STATUS.md must mention ``locked`` — Stripe and the cloud
        license host remain locked."""
        self.assertTrue(_STATUS.is_file(), "STATUS.md must exist")
        text = _STATUS.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn(
            "locked",
            lower,
            "STATUS.md must mention locked — Stripe and host remain locked",
        )

    # ------------------------------------------------------------------ #
    # 7) No Apple secrets tracked
    # ------------------------------------------------------------------ #
    def test_no_apple_secrets_tracked(self) -> None:
        """No tracked file is named ``AuthKey_*.p8`` or
        ``*notary*password*``."""
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
                    f"Tracked file {f!r} looks like an Apple AuthKey .p8 — "
                    "remove it from version control",
                )
            if "notary" in lower and "password" in lower:
                self.fail(
                    f"Tracked file {f!r} looks like a notary password "
                    "file — remove it from version control",
                )


if __name__ == "__main__":
    unittest.main()
