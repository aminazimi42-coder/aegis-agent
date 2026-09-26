"""T224 — Caged inbox image to tenant-scoped local signed PDF.

Covers:

* Happy path writes PDF + .sig under ``{tenant}/export/``.
* Path outside the tenant cage is denied (typed ``OUTSIDE_CAGE``).
* Missing file is typed ``MISSING``.
* Unsupported image type is typed ``UNSUPPORTED``.
* Neighbor tenant cannot read this tenant's PDF.
* ``forget_all`` drops that tenant's export directory.
* ``core/`` has no Stripe token.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class TestT224InboxPdf(unittest.TestCase):
    """Caged inbox image to tenant-scoped local signed PDF."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t224_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _drop_tenant_image(
        self,
        tenant: str = "t224_a",
        name: str = "photo.png",
        body: bytes = b"fake-png-bytes",
    ) -> Path:
        """Create an image under ``{tenant}/{name}`` and return its path."""
        tenant_dir = Path(self._tmp) / tenant
        tenant_dir.mkdir(parents=True, exist_ok=True)
        p = tenant_dir / name
        p.write_bytes(body)
        return p

    # ------------------------------------------------------------------ #
    # 1) Happy path writes pdf + sig under {tenant}/export
    # ------------------------------------------------------------------ #

    def test_happy_path_writes_pdf_and_sig(self) -> None:
        """build_signed_inbox_pdf writes inbox_*.pdf and inbox_*.pdf.sig."""
        from core.inbox_pdf import build_signed_inbox_pdf

        self._drop_tenant_image("t224_happy", "photo.png", b"fake-image-bytes")
        result = build_signed_inbox_pdf("t224_happy", "photo.png")

        pdf_path = Path(result["path"])
        sig_path = Path(result["sig_path"])
        self.assertTrue(pdf_path.is_file(), f"PDF missing at {pdf_path}")
        self.assertTrue(sig_path.is_file(), f".sig missing at {sig_path}")
        self.assertTrue(pdf_path.name.startswith("inbox_"))
        self.assertTrue(pdf_path.name.endswith(".pdf"))
        self.assertEqual(sig_path.name, pdf_path.name + ".sig")

        # The PDF lives under {tenant}/export/.
        self.assertIn("t224_happy", pdf_path.parent.as_posix())
        self.assertTrue(pdf_path.parent.name == "export")

        # The PDF is valid: starts with %PDF and ends with %%EOF.
        pdf_bytes = pdf_path.read_bytes()
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"%%EOF", pdf_bytes)

        # The verify status is Intact after write.
        self.assertEqual(result["verify"], "Intact")

        # The sig file contains the sha256 of the PDF bytes (detached sig).
        import hashlib

        pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
        sig_text = sig_path.read_text("utf-8")
        self.assertIn(pdf_sha, sig_text)
        self.assertIn("aegis-local", sig_text)

        # The result sha256 is the image sha (source content hash).
        expected_image_sha = hashlib.sha256(b"fake-image-bytes").hexdigest()
        self.assertEqual(result["sha256"], expected_image_sha)

    # ------------------------------------------------------------------ #
    # 2) Path outside the tenant cage denied (typed OUTSIDE_CAGE)
    # ------------------------------------------------------------------ #

    def test_path_outside_tenant_cage_denied(self) -> None:
        """An image path that resolves outside the tenant cage is denied."""
        from core.inbox_pdf import OutsideCageError, build_signed_inbox_pdf

        self._drop_tenant_image("t224_a", "photo.png")
        # A path under a different tenant's directory.
        other_tenant_dir = Path(self._tmp) / "other_tenant"
        other_tenant_dir.mkdir(parents=True, exist_ok=True)
        outside = other_tenant_dir / "image.png"
        outside.write_bytes(b"other-tenant")

        with self.assertRaises(OutsideCageError) as ctx:
            build_signed_inbox_pdf("t224_a", str(outside))
        self.assertEqual(ctx.exception.code, "OUTSIDE_CAGE")

    # ------------------------------------------------------------------ #
    # 3) Missing file typed (MISSING)
    # ------------------------------------------------------------------ #

    def test_missing_file_typed(self) -> None:
        """A non-existent file raises InboxMissingError (code MISSING)."""
        from core.inbox_pdf import InboxMissingError, build_signed_inbox_pdf

        # Tenant dir exists but the named file does not.
        tenant_dir = Path(self._tmp) / "t224_missing"
        tenant_dir.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(InboxMissingError) as ctx:
            build_signed_inbox_pdf("t224_missing", "nope.png")
        self.assertEqual(ctx.exception.code, "MISSING")

    # ------------------------------------------------------------------ #
    # 4) Unsupported image type typed (UNSUPPORTED)
    # ------------------------------------------------------------------ #

    def test_unsupported_type_typed(self) -> None:
        """A non-image file (e.g. .txt) raises UnsupportedTypeError."""
        from core.inbox_pdf import UnsupportedTypeError, build_signed_inbox_pdf

        tenant_dir = Path(self._tmp) / "t224_unsup"
        tenant_dir.mkdir(parents=True, exist_ok=True)
        (tenant_dir / "doc.txt").write_bytes(b"not an image")

        with self.assertRaises(UnsupportedTypeError) as ctx:
            build_signed_inbox_pdf("t224_unsup", "doc.txt")
        self.assertEqual(ctx.exception.code, "UNSUPPORTED")

    # ------------------------------------------------------------------ #
    # 5) Neighbor tenant cannot read this tenant's PDF
    # ------------------------------------------------------------------ #

    def test_neighbor_tenant_cannot_read(self) -> None:
        """A neighbor tenant gets OUTSIDE_CAGE or MISSING for this file.

        The image lives under tenant A's cage.  Tenant B calling with the
        same relative name cannot find it (it does not exist under B's
        cage) — typed MISSING.
        """
        from core.inbox_pdf import InboxMissingError, build_signed_inbox_pdf

        # Drop an image for tenant A.
        self._drop_tenant_image("tenant_a", "secret.png", b"tenant-a-secret")

        # Build the PDF for tenant A — succeeds.
        result_a = build_signed_inbox_pdf("tenant_a", "secret.png")
        self.assertTrue(Path(result_a["path"]).is_file())

        # Tenant B tries the same relative name — file not in B's cage.
        with self.assertRaises(InboxMissingError):
            build_signed_inbox_pdf("tenant_b", "secret.png")

    # ------------------------------------------------------------------ #
    # 6) Forget tenant drops that tenant's export
    # ------------------------------------------------------------------ #

    def test_forget_drops_tenant_export(self) -> None:
        """forget_all removes the tenant's export directory."""
        from core.inbox_pdf import build_signed_inbox_pdf
        from core.twin_memory_control import forget_all

        self._drop_tenant_image("t224_forget", "photo.png", b"forget-me")
        result = build_signed_inbox_pdf("t224_forget", "photo.png")
        export_dir = Path(result["path"]).parent
        self.assertTrue(export_dir.is_dir())

        forget_all("t224_forget")
        self.assertFalse(export_dir.exists(), "export dir still exists after forget")

    # ------------------------------------------------------------------ #
    # 7) core/ has no Stripe token
    # ------------------------------------------------------------------ #

    def test_core_has_no_stripe(self) -> None:
        """No file under core/ contains the substring 'stripe'."""
        core_dir = Path("core")
        for p in core_dir.glob("*.py"):
            text = p.read_text("utf-8")
            self.assertNotRegex(
                text,
                r"(?i)stripe",
                f"'stripe' found in {p}",
            )


if __name__ == "__main__":
    unittest.main()
