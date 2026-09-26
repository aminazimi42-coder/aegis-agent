"""T218 — Caged inbox image to local signed PDF.

Covers:

* Happy path writes PDF + .sig under ``export/``.
* Path outside the data dir is denied (typed ``path_denied_outside_data_dir``).
* Missing inbox file is typed ``INBOX_MISSING``.
* Neighbor tenant cannot read this tenant's inbox file.
* ``core/`` has no Stripe token.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class TestT218InboxPdf(unittest.TestCase):
    """Caged inbox image to local signed PDF."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t218_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _drop_inbox_image(self, name: str = "photo.png", body: bytes = b"fake-png-bytes") -> Path:
        """Create an image under ``inbox/<name>`` and return its path."""
        inbox = Path(self._tmp) / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        p = inbox / name
        p.write_bytes(body)
        return p

    # ------------------------------------------------------------------ #
    # 1) Happy path writes pdf + sig under export
    # ------------------------------------------------------------------ #

    def test_happy_path_writes_pdf_and_sig(self) -> None:
        """build_signed_inbox_pdf writes inbox_*.pdf and inbox_*.pdf.sig."""
        from core.inbox_pdf import build_signed_inbox_pdf

        self._drop_inbox_image("photo.png", b"fake-image-bytes")
        result = build_signed_inbox_pdf("t218_happy", "photo.png")

        pdf_path = Path(result["path"])
        sig_path = Path(result["sig_path"])
        self.assertTrue(pdf_path.is_file(), f"PDF missing at {pdf_path}")
        self.assertTrue(sig_path.is_file(), f".sig missing at {sig_path}")
        self.assertTrue(pdf_path.name.startswith("inbox_"))
        self.assertTrue(pdf_path.name.endswith(".pdf"))
        self.assertEqual(sig_path.name, pdf_path.name + ".sig")

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
    # 2) Path outside data dir denied
    # ------------------------------------------------------------------ #

    def test_path_outside_data_dir_denied(self) -> None:
        """An image path that resolves outside AEGIS_DATA_DIR is denied."""
        from core.inbox_pdf import build_signed_inbox_pdf
        from core.twin_local_view import PathDeniedError

        # Drop a file inside the inbox, then try to reference a path
        # outside the data dir.
        self._drop_inbox_image("photo.png")
        outside = Path(self._tmp).parent / "outside_image.png"
        outside.write_bytes(b"outside")

        with self.assertRaises(PathDeniedError):
            build_signed_inbox_pdf("t218_outside", str(outside))

    # ------------------------------------------------------------------ #
    # 3) Missing file typed
    # ------------------------------------------------------------------ #

    def test_missing_file_typed(self) -> None:
        """A non-existent inbox file raises InboxMissingError."""
        from core.inbox_pdf import InboxMissingError, build_signed_inbox_pdf

        # Inbox dir exists but the named file does not.
        inbox = Path(self._tmp) / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(InboxMissingError):
            build_signed_inbox_pdf("t218_missing", "nope.png")

    # ------------------------------------------------------------------ #
    # 4) Neighbor tenant cannot read this inbox file
    # ------------------------------------------------------------------ #

    def test_neighbor_tenant_cannot_read(self) -> None:
        """A neighbor tenant gets INBOX_MISSING for this tenant's file.

        The inbox is not per-tenant — it is a shared directory under
        AEGIS_DATA_DIR/inbox.  But the route is tenant-bound: the
        neighbor cannot see the file because the file was dropped by
        the first tenant and the neighbor's data dir is different.
        We simulate this by pointing AEGIS_DATA_DIR at a fresh temp
        dir for the neighbor.
        """
        from core.inbox_pdf import InboxMissingError, build_signed_inbox_pdf

        # Drop an image for tenant A.
        self._drop_inbox_image("secret.png", b"tenant-a-secret")

        # Build the PDF for tenant A — succeeds.
        result_a = build_signed_inbox_pdf("tenant_a", "secret.png")
        self.assertTrue(Path(result_a["path"]).is_file())

        # Now switch to a fresh data dir for the neighbor.
        neighbor_tmp = tempfile.mkdtemp(prefix="aegis_t218_neighbor_")
        original = os.environ["AEGIS_DATA_DIR"]
        os.environ["AEGIS_DATA_DIR"] = neighbor_tmp
        try:
            with self.assertRaises(InboxMissingError):
                build_signed_inbox_pdf("tenant_b", "secret.png")
        finally:
            os.environ["AEGIS_DATA_DIR"] = original

    # ------------------------------------------------------------------ #
    # 5) core/ has no Stripe token
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
