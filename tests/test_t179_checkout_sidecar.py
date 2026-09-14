"""T179 — Stripe checkout sidecar outside execute; local issuer writes entitlement.

Tests that:

* An unset ``STRIPE_SECRET_KEY`` returns ``status=not_configured`` without
  calling the network.
* The local issuer writes ``entitlement.json`` under ``AEGIS_DATA_DIR``
  with ``source``; execute sees the tier per fixture (professional or echo).
* Deleting the file -> Echo-limited (missing_file).
* Expiring the timestamp in the past -> Echo-limited (expired).
* The execute module (``core.twin_actions``) does not import stripe.
* The checkout sidecar (``app.licensing.billing_checkout``) is not called
  from ``propose()`` or ``execute()``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


class TestT179CheckoutSidecar(unittest.TestCase):
    """T179 — checkout sidecar outside execute; local issuer writes file."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = "test-key-1234567890"
        # Ensure STRIPE_SECRET_KEY is unset for each test by default.
        os.environ.pop("STRIPE_SECRET_KEY", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)
        os.environ.pop("STRIPE_SECRET_KEY", None)

    # ── 1) Unset STRIPE_SECRET_KEY -> not_configured, no network ──

    def test_checkout_unset_no_network(self) -> None:
        """create_checkout_intent returns not_configured when the key is unset."""
        os.environ.pop("STRIPE_SECRET_KEY", None)
        from app.licensing.billing_checkout import create_checkout_intent

        result = create_checkout_intent(
            "professional",
            "https://example.com/success",
            "https://example.com/cancel",
        )
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["provider"], "stripe_test_or_unset")
        self.assertIsNone(result["checkout_url"])
        # No stripe module imported.
        self.assertNotIn("stripe", sys.modules)

    # ── 2) Issuer writes file under AEGIS_DATA_DIR; execute sees tier ──

    def test_issuer_writes_data_dir(self) -> None:
        """The local issuer writes entitlement.json under AEGIS_DATA_DIR
        with source; load() sees the professional tier.
        """
        from scripts.issue_entitlement import issue

        issue("test-t1", "professional", 30, "test-key-1234567890")
        ent = Path(self._tmp) / "entitlement.json"
        self.assertTrue(ent.exists())
        data = json.loads(ent.read_text())
        self.assertEqual(data["tier"], "professional")
        self.assertEqual(data["tenant_id"], "test-t1")
        self.assertEqual(data.get("source"), "manual")
        self.assertIn("signature_sha256", data)

        # The reader accepts it.
        from core.entitlement import load

        loaded = load(tenant_id="test-t1")
        self.assertEqual(loaded["tier"], "professional")
        self.assertNotIn("reason", loaded)

    # ── 3) Delete file -> Echo-limited (missing_file) ──

    def test_delete_file_echo_limited(self) -> None:
        """When the entitlement file is deleted, load() returns missing_file."""
        from core.entitlement import load

        result = load(tenant_id="test-t1")
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "missing_file")

    # ── 4) Expired timestamp in the past -> Echo-limited (expired) ──

    def test_expired_echo_limited(self) -> None:
        """An entitlement with expires_at in the past returns expired."""
        from scripts.issue_entitlement import issue

        # Issue with 0 days so it is already expired.
        issue("test-t1", "professional", 0, "test-key-1234567890")
        from core.entitlement import load

        loaded = load(tenant_id="test-t1")
        self.assertEqual(loaded["tier"], "echo")
        self.assertEqual(loaded["reason"], "expired")

    # ── 5) Execute module does not import stripe ──

    def test_no_stripe_import_in_execute(self) -> None:
        """core.twin_actions and core.llm_safety must not import stripe."""
        import inspect

        import core.llm_safety
        import core.twin_actions

        self.assertNotIn("stripe", sys.modules)

        twin_src = inspect.getsource(core.twin_actions)
        self.assertNotIn("stripe", twin_src.lower())

        safety_src = inspect.getsource(core.llm_safety)
        self.assertNotIn("stripe", safety_src.lower())

    # ── 6) Checkout sidecar is not called from propose() or execute() ──

    def test_checkout_sidecar_not_called_from_propose_or_execute(self) -> None:
        """core.twin_actions source must not reference billing_checkout
        or create_checkout_intent.
        """
        import inspect

        import core.twin_actions

        twin_src = inspect.getsource(core.twin_actions)
        self.assertNotIn("billing_checkout", twin_src)
        self.assertNotIn("create_checkout_intent", twin_src)


if __name__ == "__main__":
    unittest.main()
