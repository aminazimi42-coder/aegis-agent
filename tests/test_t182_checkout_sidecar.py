"""T182 — Stripe checkout sidecar stays outside execute.

Tests that:

* An unset ``STRIPE_SECRET_KEY`` returns ``status=not_configured`` without
  calling the network.
* The execute module (``core.twin_actions``) does not import stripe and
  does not import the checkout sidecar (``app.licensing.billing_checkout``).
* The checkout sidecar is not called from ``propose()``.
* The README Author paragraph is untouched.
* The README does not claim the shipped app is notarized.
* No expected-failure markers or live ASGI server start.
"""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"


class TestT182CheckoutSidecar(unittest.TestCase):
    """T182 — checkout sidecar stays outside execute; live shop deferred."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t182_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("STRIPE_SECRET_KEY", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("STRIPE_SECRET_KEY", None)

    # ── 1) Unset STRIPE_SECRET_KEY -> not_configured, no network ───────

    def test_checkout_unset_no_network(self) -> None:
        """create_checkout_intent returns not_configured when the key
        is unset — no network, no stripe import."""
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
        self.assertNotIn("stripe", sys.modules)

    # ── 2) execute does not import stripe or the sidecar ─────────────

    def test_execute_does_not_import_stripe_or_sidecar(self) -> None:
        """core.twin_actions source does not import stripe or
        billing_checkout / create_checkout_intent."""
        import core.twin_actions

        twin_src = inspect.getsource(core.twin_actions)
        self.assertNotIn("stripe", twin_src.lower())
        self.assertNotIn("billing_checkout", twin_src)
        self.assertNotIn("create_checkout_intent", twin_src)

    # ── 3) checkout sidecar is not called from propose ────────────────

    def test_checkout_sidecar_not_called_from_propose(self) -> None:
        """core.twin_actions source does not reference billing_checkout
        or create_checkout_intent in any propose path."""
        import core.twin_actions

        twin_src = inspect.getsource(core.twin_actions)
        self.assertNotIn("billing_checkout", twin_src)
        self.assertNotIn("create_checkout_intent", twin_src)

    # ── 4) README Author paragraph untouched ─────────────────────────

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph retains the original identity."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)
        self.assertIn("Azimi Innovation Lab", text)

    # ── 5) README does not claim notarized ───────────────────────────

    def test_readme_does_not_claim_notarized(self) -> None:
        """README must not contain the forbidden token — the shipped app
        is not claimed to be Apple-accepted."""
        text = _README.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertNotIn("notarized", lower)

    # ── 6) No expected-failure markers or live server start ───────────

    def test_no_expected_failure_or_live_server(self) -> None:
        """This test file must not use expected-failure decorators or
        start a live ASGI server."""
        src = Path(__file__).read_text(encoding="utf-8")
        _xf = "xf" + "ail"
        _uv = "uvi" + "corn"
        self.assertNotIn(_xf, src)
        self.assertNotIn(_uv, src.lower())


if __name__ == "__main__":
    unittest.main()
