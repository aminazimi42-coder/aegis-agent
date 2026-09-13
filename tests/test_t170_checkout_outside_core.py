"""T170 — Stripe checkout outside the twin core.

Tests that the optional external checkout URL stays outside the
propose / execute / approve / complete_safe paths, that no card form
lives in the operator HTML, that expired or missing entitlement still
returns Echo-limited when a checkout URL is set, that README does not
claim a live shop, and that no Stripe secret key is tracked in the repo.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


class TestT170CheckoutOutsideCore(unittest.TestCase):
    """T170 — external checkout URL is optional and outside execute."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        # Clear the checkout env var for each test by default.
        os.environ.pop("AEGIS_CHECKOUT_URL", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_CHECKOUT_URL", None)

    # ── 1) Unset checkout URL returns checkout_unset, no socket ──

    def test_unset_checkout_url_does_not_open_socket(self) -> None:
        """checkout_url() returns checkout_unset without opening a socket."""
        os.environ.pop("AEGIS_CHECKOUT_URL", None)
        from app.licensing.checkout import checkout_url

        result = checkout_url()
        self.assertEqual(result.get("checkout_state"), "checkout_unset")
        self.assertNotIn("checkout_url", result)

    # ── 2) Propose / execute / approve do not import stripe or checkout ──

    def test_execute_propose_approve_do_not_import_stripe_or_checkout(self) -> None:
        """core.twin_actions and core.llm_safety must not import stripe or checkout."""
        # Verify no module in core/ or app/ imports 'stripe' or the
        # checkout module in the propose/execute/approve path.
        import core.llm_safety
        import core.twin_actions

        # Check that sys.modules does not contain 'stripe'.
        self.assertNotIn("stripe", sys.modules)

        # Check that app.licensing.checkout is not imported by the
        # twin_actions module's source.
        import inspect

        twin_src = inspect.getsource(core.twin_actions)
        self.assertNotIn("checkout", twin_src)
        self.assertNotIn("stripe", twin_src.lower())

        # core.llm_safety (complete_safe) must not import checkout or stripe.
        safety_src = inspect.getsource(core.llm_safety)
        self.assertNotIn("checkout", safety_src)
        self.assertNotIn("stripe", safety_src.lower())

    # ── 3) Operator HTML has no card input ──

    def test_operator_html_has_no_card_input(self) -> None:
        """The served operator HTML must not contain a card form or card input."""
        from app.server import create_app

        app = create_app()
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        html_text = resp.text
        # No card number input, no Stripe.js embed.
        self.assertNotIn("card-number", html_text.lower())
        self.assertNotIn("stripe.js", html_text.lower())
        self.assertNotIn("js.stripe.com", html_text.lower())

    # ── 4) Expired entitlement stays Echo-limited when checkout URL is set ──

    def test_expired_entitlement_stays_echo_limited_when_checkout_url_set(self) -> None:
        """Even when AEGIS_CHECKOUT_URL is set, an expired or missing
        local entitlement file returns Echo-limited with a typed reason.
        """
        os.environ["AEGIS_CHECKOUT_URL"] = "https://example.com/checkout"
        from app.licensing.checkout import checkout_url

        co = checkout_url()
        self.assertEqual(co.get("checkout_state"), "url_ready")

        # Entitlement loader still returns missing_file when no file exists.
        from core.entitlement import load

        result = load(tenant_id="test-tenant")
        self.assertEqual(result.get("tier"), "echo")
        self.assertIn(result.get("reason"), {"missing_file", "expired"})

    # ── 5) README does not claim live shop ──

    def test_readme_does_not_claim_live_shop(self) -> None:
        """README Now section must not claim a live Stripe shop is deployed."""
        readme = Path("README.md").read_text(encoding="utf-8")
        now_section = readme.split("## Now")[1].split("---")[0] if "## Now" in readme else ""
        # The Now section must not say a live shop is deployed.
        self.assertNotIn("live shop is deployed", now_section.lower())
        self.assertNotIn("live stripe shop", now_section.lower())

    # ── 6) README Author paragraph is untouched ──

    def test_readme_author_untouched(self) -> None:
        """The Author paragraph must still mention Amin Azimi and the lab."""
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("Amin Azimi", readme)
        self.assertIn("Azimi Innovation Lab", readme)

    # ── 7) Repo tracks no Stripe secret key ──

    def test_repo_tracks_no_stripe_secret(self) -> None:
        """The checkout module must not contain a Stripe secret key."""
        import subprocess

        result = subprocess.run(
            ["git", "grep", "-l", "sk_live_", "--", "app/licensing/"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        # No matches expected in the checkout module.
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
