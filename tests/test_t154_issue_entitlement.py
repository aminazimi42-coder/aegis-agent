"""T154 — Local signed entitlement issuer CLI.

Covers:

* ``test_cli_writes_signed_file_under_data_dir`` — running the CLI with a
  valid key writes ``entitlement.json`` under ``AEGIS_DATA_DIR`` with a
  valid HMAC-SHA256 signature; ``load(tenant_id=...)`` returns the
  professional tier.
* ``test_cli_refuses_without_key`` — when neither ``--key-file`` nor
  ``AEGIS_ENTITLEMENT_ISSUER_KEY`` is provided, the CLI refuses, writes
  nothing, and exits non-zero.
* ``test_broken_signature_stays_echo_limited`` — a file whose
  ``signature_sha256`` has been tampered with degrades to ``echo`` with
  ``reason="signature_mismatch"``.
* ``test_foreign_tenant_file_does_not_apply`` — a valid file whose
  ``tenant_id`` differs from the caller's tenant degrades to ``echo``
  with ``reason="tenant_mismatch"``.
* ``test_issue_module_does_not_import_stripe_or_open_socket`` — the
  issuer script source contains no ``stripe`` or ``socket`` references.

No live network.  No uvicorn.  Uses ``tmp_path``-style temp dirs; never
writes into the developer's real ``$HOME/.aegis``.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import scripts.issue_entitlement as issuer_mod
from core.entitlement import ECHO_TIER, load

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ISSUER_SCRIPT = _REPO_ROOT / "scripts" / "issue_entitlement.py"


class TestT154IssueEntitlement(unittest.TestCase):
    """Local signed entitlement issuer CLI — write, refuse, verify."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t154_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)

    # ------------------------------------------------------------------ #
    # 1) CLI writes a signed file accepted by the reader
    # ------------------------------------------------------------------ #
    def test_cli_writes_signed_file_under_data_dir(self) -> None:
        """The CLI writes a signed entitlement.json that ``load``
        accepts as professional when the tenant matches and the
        expiry is in the future."""
        key = "test-issuer-secret-t154"
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = key
        issuer_mod.issue(
            tenant_id="t154-tenant",
            tier="professional",
            days=30,
            key=key,
        )
        out_path = Path(self._tmp) / "entitlement.json"
        self.assertTrue(out_path.is_file(), "CLI must write entitlement.json")

        data = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(data["tenant_id"], "t154-tenant")
        self.assertEqual(data["tier"], "professional")
        self.assertEqual(data["issuer"], "local-cli")
        self.assertIn("signature_sha256", data)
        self.assertNotIn(key, out_path.read_text(encoding="utf-8"))

        # The reader must accept the file.
        result = load(tenant_id="t154-tenant")
        self.assertEqual(result["tier"], "professional")
        self.assertNotIn("reason", result)

    # ------------------------------------------------------------------ #
    # 2) CLI refuses without a key
    # ------------------------------------------------------------------ #
    def test_cli_refuses_without_key(self) -> None:
        """With no --key-file and no env var, the CLI writes nothing
        and exits non-zero."""
        out_path = Path(self._tmp) / "entitlement.json"
        self.assertFalse(out_path.exists(), "precondition: no file yet")

        rc = issuer_mod.main(
            ["--tenant", "t154-nokey", "--tier", "echo"]
        )
        self.assertNotEqual(rc, 0, "CLI must exit non-zero without a key")
        self.assertFalse(
            out_path.exists(),
            "CLI must not write entitlement.json without a key",
        )

    # ------------------------------------------------------------------ #
    # 3) Broken signature stays Echo-limited
    # ------------------------------------------------------------------ #
    def test_broken_signature_stays_echo_limited(self) -> None:
        """A file whose signature has been tampered with degrades to
        echo with reason='signature_mismatch'."""
        key = "test-issuer-secret-t154-break"
        issuer_mod.issue(
            tenant_id="t154-broken",
            tier="professional",
            days=30,
            key=key,
        )
        out_path = Path(self._tmp) / "entitlement.json"
        data = json.loads(out_path.read_text(encoding="utf-8"))
        data["signature_sha256"] = "0" * 64
        out_path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # Set the key so the reader can attempt HMAC verification.
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = key
        result = load(tenant_id="t154-broken")
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(result["reason"], "signature_mismatch")

    # ------------------------------------------------------------------ #
    # 4) Foreign tenant file does not apply
    # ------------------------------------------------------------------ #
    def test_foreign_tenant_file_does_not_apply(self) -> None:
        """A valid file whose tenant_id differs from the caller's
        tenant degrades to echo with reason='tenant_mismatch'."""
        key = "test-issuer-secret-t154-foreign"
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = key
        issuer_mod.issue(
            tenant_id="other-tenant",
            tier="professional",
            days=30,
            key=key,
        )
        result = load(tenant_id="t154-tenant")
        self.assertEqual(result["tier"], ECHO_TIER)
        self.assertEqual(result["reason"], "tenant_mismatch")

    # ------------------------------------------------------------------ #
    # 5) Issue module does not import stripe or open a socket
    # ------------------------------------------------------------------ #
    def test_issue_module_does_not_import_stripe_or_open_socket(self) -> None:
        """The issuer script source contains no 'stripe' or 'socket'
        references."""
        text = _ISSUER_SCRIPT.read_text(encoding="utf-8").lower()
        self.assertNotIn("stripe", text)
        self.assertNotIn("socket", text)


if __name__ == "__main__":
    unittest.main()
