"""T168 — Notary guard: notarytool locked until a real ticket exists.

Covers:

* ``test_script_exists`` — ``scripts/codesign_operator.sh`` exists.
* ``test_unsigned_path_still_present`` — the script still prints
  ``UNSIGNED`` when no Developer ID identity is found.
* ``test_signed_print_requires_verify`` — the script prints
  ``SIGNED`` only after ``codesign --verify --deep --strict`` succeeds.
* ``test_script_does_not_call_notarytool`` — the script does not invoke
  ``notarytool`` as a command.
* ``test_script_prints_notary_locked_until_ticket`` — the script prints
  ``NOTARY_LOCKED_UNTIL_TICKET`` and does not contain
  ``NOTARY_LOCKED_UNTIL_T168``.
* ``test_readme_does_not_claim_app_is_notarized`` — README does not
  contain ``notarized``.
* ``test_status_keeps_stripe_and_host_locked`` — STATUS.md mentions
  ``locked``.

No uvicorn subprocess.  No network.  Does not run notarytool against
Apple.  Does not require a real certificate in CI.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "codesign_operator.sh"
_README = REPO_ROOT / "README.md"
_STATUS = REPO_ROOT / "STATUS.md"


class TestT168NotaryGuard(unittest.TestCase):
    """T168 — notarytool locked until a real ticket exists."""

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
        path — T167_CONTINUE does not weaken the unsigned guard."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "UNSIGNED",
            text,
            "Script must still mention UNSIGNED for the no-identity path",
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
        # The SIGNED echo must appear after the verify call.
        lines = text.splitlines()
        verify_line: int | None = None
        for i, line in enumerate(lines):
            if "codesign --verify --deep --strict" in line:
                verify_line = i
                break
        signed_line: int | None = None
        for i, line in enumerate(lines):
            if "SIGNED" in line and "echo" in line:
                signed_line = i
                break
        self.assertIsNotNone(verify_line, "Script must have a verify line")
        self.assertIsNotNone(signed_line, "Script must have a SIGNED echo line")
        assert verify_line is not None
        assert signed_line is not None
        self.assertGreater(
            signed_line,
            verify_line,
            "SIGNED must appear after codesign --verify, not before",
        )

    # ------------------------------------------------------------------ #
    # 4) Script does not invoke notarytool
    # ------------------------------------------------------------------ #
    def test_script_does_not_call_notarytool(self) -> None:
        """The script must not invoke ``notarytool`` as a command."""
        text = _SCRIPT.read_text(encoding="utf-8")
        # Filter to non-comment lines and check that no line runs
        # notarytool as a shell command.
        code_lines = [
            line for line in text.splitlines()
            if not line.strip().startswith("#")
        ]
        code_text = "\n".join(code_lines)
        self.assertNotIn(
            "notarytool",
            code_text,
            "Script must not invoke notarytool",
        )
        self.assertNotIn(
            "stapler",
            code_text,
            "Script must not invoke stapler",
        )

    # ------------------------------------------------------------------ #
    # 5) Script prints NOTARY_LOCKED_UNTIL_TICKET
    # ------------------------------------------------------------------ #
    def test_script_prints_notary_locked_until_ticket(self) -> None:
        """The script must print ``NOTARY_LOCKED_UNTIL_TICKET`` and
        must not contain ``NOTARY_LOCKED_UNTIL_T168``."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "NOTARY_LOCKED_UNTIL_TICKET",
            text,
            "Script must print NOTARY_LOCKED_UNTIL_TICKET",
        )
        self.assertNotIn(
            "NOTARY_LOCKED_UNTIL_T168",
            text,
            "Script must not contain NOTARY_LOCKED_UNTIL_T168",
        )

    # ------------------------------------------------------------------ #
    # 6) README does not claim the app is notarized
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
    # 7) STATUS keeps Stripe and host locked
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
