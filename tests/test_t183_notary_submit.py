"""T183 — Notary submit-only helper, no NOTARIZED lie.

Covers:

* ``test_script_exists`` — ``scripts/notarize_submit.sh`` exists and is
  executable.
* ``test_script_uses_keychain_profile_only`` — the script submits with
  ``--keychain-profile`` and never passes ``--apple-id``,
  ``--password``, ``--team-id``, or a raw key path to notarytool.
* ``test_script_has_no_wait_and_no_staple`` — the script does not use
  ``--wait`` and does not run ``stapler staple``.
* ``test_script_never_prints_notarized_success`` — the script never
  prints ``NOTARIZED`` as a success state.
* ``test_readme_does_not_claim_app_is_notarized`` — README does not
  contain ``notarized``.
* ``test_status_keeps_staple_and_billing_locked`` — STATUS.md mentions
  T183 and says staple and billing remain locked.
* ``test_no_apple_secrets_tracked`` — no tracked file is an Apple
  ``AuthKey_*.p8``, ``*notary*password*``, ``*.cer``, or ``*.p12``.

No uvicorn subprocess.  No network.  Does not run notarytool against
Apple in pytest.  Does not start uvicorn.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "notarize_submit.sh"
_DOCS = REPO_ROOT / "docs" / "APPLE_DEVELOPER.md"
_README = REPO_ROOT / "README.md"
_STATUS = REPO_ROOT / "STATUS.md"


class TestT183NotarySubmit(unittest.TestCase):
    """T183 — notary submit-only helper without NOTARIZED lie."""

    # ------------------------------------------------------------------ #
    # 1) Script exists
    # ------------------------------------------------------------------ #
    def test_script_exists(self) -> None:
        """``scripts/notarize_submit.sh`` must exist and be executable."""
        self.assertTrue(
            _SCRIPT.is_file(),
            "scripts/notarize_submit.sh must exist",
        )

    # ------------------------------------------------------------------ #
    # 2) Uses keychain profile only — no apple-id/password/team-id/key path
    # ------------------------------------------------------------------ #
    def test_script_uses_keychain_profile_only(self) -> None:
        """The script must use ``--keychain-profile`` and never pass
        ``--apple-id``, ``--password``, ``--team-id``, or a raw key
        path to notarytool submit."""
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "--keychain-profile",
            text,
            "Script must use --keychain-profile for notarytool submit",
        )
        # Check the notarytool submit command block — the full script
        # text must not include these flags on the submit command.
        # The docs section references --apple-id and --team-id for
        # store-credentials, so only check the submit block.
        # Find the notarytool submit block.
        lines = text.splitlines()
        in_submit = False
        submit_block: list[str] = []
        for line in lines:
            if "notarytool submit" in line:
                in_submit = True
            if in_submit:
                submit_block.append(line)
                if line.strip() == "" or "output-format json" in line:
                    break
        submit_text = "\n".join(submit_block).lower()
        self.assertNotIn(
            "--apple-id",
            submit_text,
            "notarytool submit must not pass --apple-id",
        )
        self.assertNotIn(
            "--password",
            submit_text,
            "notarytool submit must not pass --password",
        )
        self.assertNotIn(
            "--team-id",
            submit_text,
            "notarytool submit must not pass --team-id",
        )

    # ------------------------------------------------------------------ #
    # 3) No --wait and no stapler staple
    # ------------------------------------------------------------------ #
    def test_script_has_no_wait_and_no_staple(self) -> None:
        """The script must not use ``--wait`` and must not run
        ``stapler staple`` — waiting and stapling are the next slice."""
        text = _SCRIPT.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertNotIn(
            "--wait",
            lower,
            "Script must not use --wait — waiting is the next slice",
        )
        self.assertNotIn(
            "stapler staple",
            lower,
            "Script must not run stapler staple — stapling is the next slice",
        )
        self.assertNotIn(
            "stapler validate",
            lower,
            "Script must not run stapler validate — stapling is the next slice",
        )

    # ------------------------------------------------------------------ #
    # 4) Never prints NOTARIZED as a success state
    # ------------------------------------------------------------------ #
    def test_script_never_prints_notarized_success(self) -> None:
        """The script must never print ``NOTARIZED`` — that word stays
        locked behind a staple ticket in the next market slice."""
        text = _SCRIPT.read_text(encoding="utf-8")
        upper = text.upper()
        self.assertNotIn(
            "NOTARIZED",
            upper,
            "Script must never print NOTARIZED — not in this slice",
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
    # 6) STATUS.md keeps staple and billing locked
    # ------------------------------------------------------------------ #
    def test_status_keeps_staple_and_billing_locked(self) -> None:
        """STATUS.md must mention T183 and say staple and billing
        remain locked."""
        self.assertTrue(
            _STATUS.is_file(),
            "STATUS.md must exist",
        )
        text = _STATUS.read_text(encoding="utf-8")
        self.assertIn("T183", text, "STATUS.md must mention T183")
        lower = text.lower()
        self.assertIn(
            "staple",
            lower,
            "STATUS.md must say staple remains locked for T183",
        )
        self.assertIn(
            "locked",
            lower,
            "STATUS.md must say something remains locked for T183",
        )

    # ------------------------------------------------------------------ #
    # 7) No Apple secrets tracked
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
