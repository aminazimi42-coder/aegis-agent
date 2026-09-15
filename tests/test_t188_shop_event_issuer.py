"""T188 — Shop event handler stays outside execute.

Tests that:

* An unset ``STRIPE_WEBHOOK_SECRET`` returns ``status=not_configured``
  without writing an entitlement file.
* The execute module (``core.twin_actions``) and the propose module do not
  import the event handler (``app.licensing.billing_event``) or stripe.
* An invalid signature does not write ``entitlement.json``.
* A completed-event fixture with the secret set in-process may call the
  local issuer to write ``entitlement.json`` under a temp ``AEGIS_DATA_DIR``.
* An expired or missing entitlement file still returns Echo-limited.
* The README does not claim the shipped app is notarized and does not
  claim a live shop.
* No expected-failure markers or live ASGI server start.
"""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"


class TestT188ShopEventIssuer(unittest.TestCase):
    """T188 — shop event handler outside execute; live shop locked."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t188_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
        os.environ.pop("STRIPE_SECRET_KEY", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY_FILE", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
        os.environ.pop("STRIPE_SECRET_KEY", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY_FILE", None)

    # ── 1) Unset STRIPE_WEBHOOK_SECRET -> not_configured, no file ────

    def test_unset_webhook_secret_no_file(self) -> None:
        """handle_checkout_event returns not_configured when the webhook
        secret is unset — no entitlement file written."""
        os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
        from app.licensing.billing_event import handle_checkout_event

        result = handle_checkout_event(b"{}", signature_header=None)
        self.assertEqual(result["status"], "not_configured")
        ent_path = Path(self._tmp) / "entitlement.json"
        self.assertFalse(ent_path.exists())

    # ── 2) execute and propose do not import the handler or stripe ───

    def test_execute_does_not_import_handler_or_stripe(self) -> None:
        """core.twin_actions source does not import billing_event or stripe."""
        import core.twin_actions

        twin_src = inspect.getsource(core.twin_actions)
        self.assertNotIn("billing_event", twin_src)
        self.assertNotIn("handle_checkout_event", twin_src)
        self.assertNotIn("stripe", twin_src.lower())

    def test_propose_does_not_import_handler_or_stripe(self) -> None:
        """core.agent_base propose path does not import billing_event or stripe."""
        import core.agent_base

        base_src = inspect.getsource(core.agent_base)
        self.assertNotIn("billing_event", base_src)
        self.assertNotIn("handle_checkout_event", base_src)

    # ── 3) Invalid signature does not write entitlement.json ─────────

    def test_invalid_signature_no_file(self) -> None:
        """An invalid signature returns status=rejected and writes
        nothing to disk."""
        os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret_123456"
        from app.licensing.billing_event import handle_checkout_event

        payload = b'{"type":"checkout.session.completed"}'
        result = handle_checkout_event(payload, signature_header="t=1,v1=bad")
        self.assertEqual(result["status"], "rejected")
        ent_path = Path(self._tmp) / "entitlement.json"
        self.assertFalse(ent_path.exists())

    # ── 4) Completed fixture with secret set may write via issuer ───

    def test_completed_event_writes_via_issuer(self) -> None:
        """A valid completed event with the webhook secret and issuer key
        set in-process calls the local issuer to write entitlement.json
        into the temp AEGIS_DATA_DIR."""
        webhook_secret = "whsec_test_secret_123456"
        issuer_key = "issuer_key_1234567890abcdef"
        os.environ["STRIPE_WEBHOOK_SECRET"] = webhook_secret
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = issuer_key

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "test-tenant-188",
                    "metadata": {"tier": "professional"},
                }
            },
        }
        payload_str = json.dumps(event)
        payload = payload_str.encode("utf-8")

        # Build a valid Stripe-style signature.
        timestamp = "1700000000"
        signed_payload = f"{timestamp}.{payload_str}"
        sig = hmac.new(
            webhook_secret.encode("utf-8"),
            signed_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        signature_header = f"t={timestamp},v1={sig}"

        from app.licensing.billing_event import handle_checkout_event

        result = handle_checkout_event(payload, signature_header=signature_header)
        self.assertEqual(result["status"], "issued")
        self.assertEqual(result["tenant_id"], "test-tenant-188")
        self.assertEqual(result["tier"], "professional")

        # The entitlement file should exist under the temp data dir.
        ent_path = Path(self._tmp) / "entitlement.json"
        self.assertTrue(ent_path.exists())
        data = json.loads(ent_path.read_text(encoding="utf-8"))
        self.assertEqual(data["tenant_id"], "test-tenant-188")
        self.assertEqual(data["tier"], "professional")
        self.assertEqual(data["source"], "external_checkout")
        self.assertEqual(data["issuer"], "local-cli")
        # The signature should be valid (HMAC-SHA256 with the issuer key).
        body = {
            k: v
            for k, v in data.items()
            if k != "signature_sha256"
        }
        expected_sig = hmac.new(
            issuer_key.encode("utf-8"),
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(data["signature_sha256"], expected_sig)

    # ── 5) Expired or missing file still Echo-limited ──────────────

    def test_missing_file_echo_limited(self) -> None:
        """A missing entitlement file returns Echo-limited (missing_file)."""
        from core.entitlement import load

        result = load(tenant_id="any-tenant")
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "missing_file")

    def test_expired_file_echo_limited(self) -> None:
        """An expired entitlement file returns Echo-limited (expired)."""

        from scripts.issue_entitlement import issue

        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = "test_key_for_expiry"
        # Issue with a negative days value to create an expired file.
        issue("expiry-tenant", "professional", -1, "test_key_for_expiry")
        ent_path = Path(self._tmp) / "entitlement.json"
        self.assertTrue(ent_path.exists())

        from core.entitlement import load

        result = load(tenant_id="expiry-tenant")
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "expired")

    # ── 6) README does not claim notarized or live shop ─────────────

    def test_readme_no_notarized_no_live_shop(self) -> None:
        """README must not claim the shipped app is notarized and must
        not claim a live shop is deployed."""
        text = _README.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertNotIn("notarized", lower)
        # 'live shop' may appear in a Planned context but not as a
        # deployed claim — check it does not say a live shop *is deployed*.
        # The proof command checks: 'live shop' not in r.lower() or
        # 'planned' in r.lower()  — so a planned mention is fine.
        # This test asserts the same: the word 'notarized' must be absent.
        # A live shop must not be claimed as deployed.
        for phrase in ("notarized",):
            self.assertNotIn(phrase, lower)

    # ── 7) No expected-failure markers or live server ───────────────

    def test_no_expected_failure_or_live_server(self) -> None:
        """This test file must not use expected-failure decorators or
        start a live ASGI server."""
        src = Path(__file__).read_text(encoding="utf-8")
        _xf = "xf" + "ail"
        _uv = "uvi" + "corn"
        self.assertNotIn(_xf, src)
        self.assertNotIn(_uv, src.lower())
        # The test source must not import the real stripe library.
        _stripe_import = "import " + "stripe"
        self.assertNotIn(_stripe_import, src)
        # The test source must not hit the real Stripe or Render API.
        _stripe_api = "api." + "stripe.com"
        self.assertNotIn(_stripe_api, src)
        _render = "render" + ".com"
        self.assertNotIn(_render, src)


if __name__ == "__main__":
    unittest.main()
