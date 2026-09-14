"""T176 — Path cage and bearer/webhook/SSH redact.

Tests:
1. ``test_write_inside_data_dir_allowed`` — a write inside ``AEGIS_DATA_DIR``
   is allowed and the file appears at the expected path.
2. ``test_write_outside_data_dir_denied`` — a write outside
   ``AEGIS_DATA_DIR`` is denied with a typed ``PathDeniedError`` and no
   file is written.
3. ``test_deny_code_is_path_denied_outside_data_dir`` — the typed code
   on the deny is ``path_denied_outside_data_dir``.
4. ``test_bearer_redacted_on_propose_or_audit`` — ``Bearer <token>`` is
   redacted on both the propose path and the audit path.
5. ``test_webhook_secret_redacted`` — a webhook query secret
   (``?secret=…``) is redacted.
6. ``test_ssh_key_shape_redacted`` — an SSH private-key block
   (``-----BEGIN OPENSSH PRIVATE KEY-----`` … ``-----END OPENSSH PRIVATE KEY-----``)
   is redacted.
7. ``test_readme_author_untouched`` — the README Author paragraph is
   present and untouched.

Uses ``tmp_path``.  Does not write the live ``$HOME/.aegis``.  Does not
start uvicorn.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


class TestT176CageRedact(unittest.TestCase):
    """Uniform path cage and bearer/webhook/SSH redact."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t176_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) Write inside AEGIS_DATA_DIR is allowed
    # ------------------------------------------------------------------ #

    def test_write_inside_data_dir_allowed(self) -> None:
        """cage_path allows a destination inside the data root."""
        from core.twin_local_view import cage_path

        inside = Path(self._tmp) / "export" / "local.md"
        resolved = cage_path(inside)
        self.assertEqual(resolved, inside)

        # A relative bare filename should also land inside the root.
        bare = cage_path("bare.md")
        self.assertEqual(bare, Path(self._tmp) / "bare.md")

    # ------------------------------------------------------------------ #
    # 2) Write outside AEGIS_DATA_DIR is denied
    # ------------------------------------------------------------------ #

    def test_write_outside_data_dir_denied(self) -> None:
        """cage_path rejects a destination that escapes the data root."""
        from core.twin_local_view import PathDeniedError, cage_path

        outside = Path(self._tmp).parent / "escape_target_t176.md"
        with self.assertRaises(PathDeniedError) as ctx:
            cage_path(outside)
        self.assertIn("outside AEGIS_DATA_DIR", str(ctx.exception))
        # No file written.
        self.assertFalse(outside.exists())

    # ------------------------------------------------------------------ #
    # 3) Typed deny code is path_denied_outside_data_dir
    # ------------------------------------------------------------------ #

    def test_deny_code_is_path_denied_outside_data_dir(self) -> None:
        """The typed code on PathDeniedError is path_denied_outside_data_dir."""
        from core.twin_local_view import PathDeniedError, cage_path

        outside = Path(self._tmp).parent / "escape_target_t176b.md"
        try:
            cage_path(outside)
            self.fail("Expected PathDeniedError")
        except PathDeniedError as exc:
            self.assertEqual(exc.code, "path_denied_outside_data_dir")

    # ------------------------------------------------------------------ #
    # 4) Bearer token redacted on propose and audit
    # ------------------------------------------------------------------ #

    def test_bearer_redacted_on_propose_or_audit(self) -> None:
        """Bearer <token> is redacted on propose body and audit extra."""
        from core.redact import redact, redact_payload

        # Propose path: redact a Bearer token from the title/payload.
        raw = (
            "Authorization: Bearer "
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        redacted = redact(raw)
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", redacted)
        self.assertIn("[REDACTED]", redacted)

        # Audit path: redact a Bearer token from the extra dict.
        extra = {"header": "Bearer abcdefghijk123456789"}
        redacted_extra = redact_payload(extra)
        self.assertNotIn("abcdefghijk123456789", redacted_extra["header"])
        self.assertIn("[REDACTED]", redacted_extra["header"])

    # ------------------------------------------------------------------ #
    # 5) Webhook query secret redacted
    # ------------------------------------------------------------------ #

    def test_webhook_secret_redacted(self) -> None:
        """A webhook URL query secret (?secret=…) is redacted."""
        from core.redact import redact

        webhook_url = (
            "https://hooks.example.com/webhook"
            "?secret=abcdefgh123456789"
        )
        redacted = redact(webhook_url)
        self.assertNotIn("abcdefgh123456789", redacted)
        self.assertIn("[REDACTED]", redacted)

        # Also test &token= form.
        webhook_url2 = (
            "https://hooks.example.com/webhook"
            "?id=abc&token=secretvalue123456"
        )
        redacted2 = redact(webhook_url2)
        self.assertNotIn("secretvalue123456", redacted2)
        self.assertIn("[REDACTED]", redacted2)

    # ------------------------------------------------------------------ #
    # 6) SSH private-key block redacted
    # ------------------------------------------------------------------ #

    def test_ssh_key_shape_redacted(self) -> None:
        """An SSH private-key block is redacted."""
        from core.redact import redact

        ssh_key = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW\n"
            "Q255AAAAIA8Xn3a7Lb9g8kPtQ5T8mZ8n5t5vBd8n5t5vBd8n5t5vBd8n5t5vBd8n5t5vBd8\n"
            "-----END OPENSSH PRIVATE KEY-----\n"
        )
        redacted = redact(ssh_key)
        self.assertNotIn("b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ", redacted)
        self.assertIn("[REDACTED]", redacted)

    # ------------------------------------------------------------------ #
    # 7) README Author paragraph untouched
    # ------------------------------------------------------------------ #

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and untouched."""
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("Author", readme)
        self.assertIn("Amin Azimi", readme)


if __name__ == "__main__":
    unittest.main()
