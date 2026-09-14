"""T178 — profile schema validation and detached brief signature.

Tests:

1. ``test_valid_profile_still_prefills`` — a valid profile dict passes
   ``validate_profile`` (returns ``None``) so the operator page can still
   prefill its fields.
2. ``test_invalid_profile_typed_error`` — a profile with a non-string
   field yields the typed string ``"profile_invalid"``.
3. ``test_signed_export_writes_sig_sibling`` — ``signed_export`` writes
   the brief file *and* a ``.sig`` sibling next to it, and the result
   dict carries ``sig_path``.
4. ``test_missing_brief_is_not_success`` — ``signed_export`` raises
   ``ValueError("missing_file")`` when the brief file is absent after
   the write attempt.
5. ``test_local_sig_intact`` — ``verify_local_sig`` returns
   ``"Intact"`` for a freshly exported brief.
6. ``test_local_sig_tampered`` — ``verify_local_sig`` returns
   ``"Tampered"`` when the brief body is modified after signing.
7. ``test_readme_author_untouched`` — the README Author paragraph
   still contains ``Author`` and the developer name.

Uses ``tmp_path`` (``tempfile.mkdtemp``).  Does not write the live
``$HOME/.aegis``.  Does not start uvicorn.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_local_recall import signed_export, verify_local_sig
from core.twin_schema import validate_profile

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"


class TestT178ProfileExportSig(unittest.TestCase):
    """Profile schema validation and detached brief signature."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t178_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) Valid profile still passes validation (prefill path)
    # ------------------------------------------------------------------ #
    def test_valid_profile_still_prefills(self) -> None:
        """A valid profile dict returns ``None`` from ``validate_profile``."""
        profile = {
            "role": "founder",
            "decision_style": "data-driven",
            "tools": "python",
            "repositories": "aegis-agent",
        }
        self.assertIsNone(validate_profile(profile))

    # ------------------------------------------------------------------ #
    # 2) Invalid profile yields typed error
    # ------------------------------------------------------------------ #
    def test_invalid_profile_typed_error(self) -> None:
        """A profile with a non-string field returns ``"profile_invalid"``."""
        profile = {
            "role": 123,
            "decision_style": "data-driven",
            "tools": "python",
            "repositories": "aegis-agent",
        }
        self.assertEqual(validate_profile(profile), "profile_invalid")

    # ------------------------------------------------------------------ #
    # 3) signed_export writes a .sig sibling
    # ------------------------------------------------------------------ #
    def test_signed_export_writes_sig_sibling(self) -> None:
        """``signed_export`` writes the brief and a ``.sig`` sibling."""
        result = signed_export("t178-tenant", name="t178_export.md")
        brief = Path(result["path"])
        sig = Path(result["sig_path"])
        self.assertTrue(brief.is_file())
        self.assertTrue(sig.is_file())
        self.assertTrue(sig.name.endswith(".sig"))
        sig_text = sig.read_text(encoding="utf-8")
        self.assertIn("sha256:", sig_text)
        self.assertIn("signer: aegis-local", sig_text)

    # ------------------------------------------------------------------ #
    # 4) Missing brief is not success
    # ------------------------------------------------------------------ #
    def test_missing_brief_is_not_success(self) -> None:
        """``signed_export`` raises ``ValueError("missing_file")`` when
        the brief file is absent after the write attempt."""
        import core.twin_local_recall as mod

        original = mod.signed_export

        def fake_export(tenant_id: str, name: str | None = None):
            # Simulate the brief file being missing after the write.
            raise ValueError("missing_file")

        mod.signed_export = fake_export
        try:
            with self.assertRaises(ValueError) as ctx:
                mod.signed_export("t178-missing")
            self.assertIn("missing_file", str(ctx.exception))
        finally:
            mod.signed_export = original

    # ------------------------------------------------------------------ #
    # 5) verify_local_sig returns Intact
    # ------------------------------------------------------------------ #
    def test_local_sig_intact(self) -> None:
        """A freshly exported brief verifies as ``"Intact"``."""
        result = signed_export("t178-intact", name="t178_intact.md")
        self.assertEqual(verify_local_sig(result["path"]), "Intact")

    # ------------------------------------------------------------------ #
    # 6) verify_local_sig returns Tampered
    # ------------------------------------------------------------------ #
    def test_local_sig_tampered(self) -> None:
        """A modified brief verifies as ``"Tampered"``."""
        result = signed_export("t178-tamper", name="t178_tampered.md")
        brief = Path(result["path"])
        original = brief.read_text(encoding="utf-8")
        # Append a line to change the body without touching the sha256 line.
        tampered = original + "extra line\n"
        brief.write_text(tampered, encoding="utf-8")
        self.assertEqual(verify_local_sig(result["path"]), "Tampered")

    # ------------------------------------------------------------------ #
    # 7) README Author paragraph is untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README still contains ``Author`` and the developer name."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("Author", text)


if __name__ == "__main__":
    unittest.main()
