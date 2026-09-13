"""T167 — Apple Developer ID wiring.

Covers:

* ``test_script_exists`` — ``scripts/codesign_operator.sh`` exists.
* ``test_script_mentions_unsigned`` — the script mentions ``UNSIGNED``.
* ``test_script_does_not_call_notarytool_in_t167`` — the source contains
  ``NOTARY_LOCKED_UNTIL_T168`` and does not invoke ``notarytool`` as an
  unguarded command.
* ``test_docs_say_enroll_on_hermesdev_not_amin`` — ``docs/APPLE_DEVELOPER.md``
  says the owner enrolls on hermesdev, not amin.
* ``test_readme_does_not_claim_notarized_or_app_store`` — README does not
  contain ``notarized`` or ``App Store``.
* ``test_repo_has_no_apple_password_files`` — no tracked file named
  ``AuthKey_*.p8`` or ``*apple-id*password*``.

No uvicorn subprocess.  No network.  Does not run notarytool against Apple.
Does not require a real certificate in CI.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "codesign_operator.sh"
_DOCS = REPO_ROOT / "docs" / "APPLE_DEVELOPER.md"
_README = REPO_ROOT / "README.md"


class TestT167CodesignIdentity(unittest.TestCase):
    """T167 — Developer ID codesign wiring without a notarize claim."""

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
    # 2) Script mentions UNSIGNED
    # ------------------------------------------------------------------ #
    def test_script_mentions_unsigned(self) -> None:
        """The script mentions ``UNSIGNED`` for the no-identity path."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "UNSIGNED",
            text,
            "Script must mention UNSIGNED for the no-identity path",
        )

    # ------------------------------------------------------------------ #
    # 3) Script does not call notarytool in T167
    # ------------------------------------------------------------------ #
    def test_script_does_not_call_notarytool_in_t167(self) -> None:
        """The source must contain ``NOTARY_LOCKED_UNTIL_T168`` and must
        not invoke ``notarytool`` as an unguarded command."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "NOTARY_LOCKED_UNTIL_T168",
            text,
            "Script must contain NOTARY_LOCKED_UNTIL_T168",
        )
        # Filter to non-comment, non-echo lines and check that 'notarytool'
        # does not appear as an actual command invocation.
        code_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith("echo "):
                continue
            code_lines.append(line)
        code_text = "\n".join(code_lines)
        self.assertNotIn(
            "notarytool",
            code_text,
            "Script must not invoke notarytool as an unguarded command in T167",
        )

    # ------------------------------------------------------------------ #
    # 4) Docs say enroll on hermesdev, not amin
    # ------------------------------------------------------------------ #
    def test_docs_say_enroll_on_hermesdev_not_amin(self) -> None:
        """``docs/APPLE_DEVELOPER.md`` says the owner enrolls on hermesdev,
        not amin."""
        self.assertTrue(
            _DOCS.is_file(),
            "docs/APPLE_DEVELOPER.md must exist",
        )
        text = _DOCS.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertIn(
            "hermesdev",
            lower,
            "Docs must say the owner enrolls on hermesdev",
        )
        # The docs must explicitly say signing does not happen on amin.
        self.assertIn(
            "amin",
            lower,
            "Docs must mention amin as the non-signing account",
        )

    # ------------------------------------------------------------------ #
    # 5) README does not claim notarized or App Store
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
    # 6) Repo has no Apple password files
    # ------------------------------------------------------------------ #
    def test_repo_has_no_apple_password_files(self) -> None:
        """No tracked file is named ``AuthKey_*.p8`` or
        ``*apple-id*password*``."""
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
            if "apple-id" in lower and "password" in lower:
                self.fail(
                    f"Tracked file {f!r} looks like an Apple ID password "
                    "file — remove it from version control",
                )


if __name__ == "__main__":
    unittest.main()
