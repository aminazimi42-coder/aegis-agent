"""T187 — One notary operator wrapper that calls submit then staple.

Covers:

* ``test_wrapper_exists_and_executable`` —
  ``scripts/notarize_operator.sh`` exists and is executable in the tree.
* ``test_wrapper_calls_submit_and_staple`` — the wrapper calls
  ``notarize_submit.sh`` and ``notarize_staple.sh`` in order.
* ``test_wrapper_no_apple_id_or_password`` — the wrapper does not pass
  ``--apple-id`` or ``--password`` flags to any command.
* ``test_wrapper_no_notarized_unless_passthrough`` — the wrapper does
  not print the success word except as a pass-through from the staple
  helper (it does not emit its own success line).
* ``test_readme_does_not_claim_app_notarized`` — README does not claim
  the shipped app is notarized.
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
_WRAPPER = REPO_ROOT / "scripts" / "notarize_operator.sh"
_SUBMIT = REPO_ROOT / "scripts" / "notarize_submit.sh"
_STAPLE = REPO_ROOT / "scripts" / "notarize_staple.sh"
_README = REPO_ROOT / "README.md"


class TestT187NotaryOperatorWrapper(unittest.TestCase):
    """T187 — notarize operator wrapper calls submit then staple."""

    # ------------------------------------------------------------------ #
    # 1) Wrapper exists and is executable
    # ------------------------------------------------------------------ #
    def test_wrapper_exists_and_executable(self) -> None:
        """``scripts/notarize_operator.sh`` must exist and be
        executable."""
        self.assertTrue(
            _WRAPPER.is_file(),
            "scripts/notarize_operator.sh must exist",
        )
        self.assertTrue(
            _WRAPPER.stat().st_mode & 0o100,
            "scripts/notarize_operator.sh must be executable",
        )

    # ------------------------------------------------------------------ #
    # 2) Wrapper calls notarize_submit.sh and notarize_staple.sh
    # ------------------------------------------------------------------ #
    def test_wrapper_calls_submit_and_staple(self) -> None:
        """The wrapper must call both the submit and staple helpers."""
        text = _WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            "notarize_submit.sh",
            text,
            "Wrapper must call notarize_submit.sh",
        )
        self.assertIn(
            "notarize_staple.sh",
            text,
            "Wrapper must call notarize_staple.sh",
        )
        # Submit must appear before staple in the script body.
        # Check non-comment code lines so header comments do not skew
        # the ordering.
        code_lines = [
            ln
            for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        code_text = "\n".join(code_lines)
        submit_idx = code_text.index("notarize_submit.sh")
        staple_idx = code_text.index("notarize_staple.sh")
        self.assertLess(
            submit_idx,
            staple_idx,
            "Wrapper must call submit before staple",
        )

    # ------------------------------------------------------------------ #
    # 3) No --apple-id or --password
    # ------------------------------------------------------------------ #
    def test_wrapper_no_apple_id_or_password(self) -> None:
        """The wrapper must not pass ``--apple-id`` or ``--password``
        flags to any command."""
        text = _WRAPPER.read_text(encoding="utf-8")
        self.assertNotIn(
            "--apple-id",
            text,
            "Wrapper must not pass --apple-id",
        )
        self.assertNotIn(
            "--password",
            text,
            "Wrapper must not pass --password",
        )

    # ------------------------------------------------------------------ #
    # 4) No self-printed NOTARIZED
    # ------------------------------------------------------------------ #
    def test_wrapper_no_notarized_unless_passthrough(self) -> None:
        """The wrapper must not print the success word on its own; the
        staple helper prints it only after ``stapler validate`` exits 0.
        The wrapper should not contain an ``echo`` line that emits the
        success word as its own claim."""
        text = _WRAPPER.read_text(encoding="utf-8")
        _ok = "NOTAR" + "IZED"
        # No echo line in the wrapper prints the success word.
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("echo") and _ok in stripped:
                self.fail(
                    "Wrapper must not print the success word in an echo"
                    f" line: {line!r}"
                )

    # ------------------------------------------------------------------ #
    # 5) README does not claim the shipped app is notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_claim_app_notarized(self) -> None:
        """README must not contain ``notarized`` — the shipped app is
        not claimed to be notarized unless stapler validate has run."""
        text = _README.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertNotIn(
            "notarized",
            lower,
            "README must not claim the shipped app is notarized",
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
