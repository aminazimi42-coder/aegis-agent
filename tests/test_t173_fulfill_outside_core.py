"""T173 — Grant-gated local fulfill outside the twin core.

Tests that:

* A wrong or empty grant writes nothing (typed refuse).
* A missing issuer key writes nothing (typed refuse).
* A valid grant + key writes a signed ``entitlement.json`` under a temp
  ``AEGIS_DATA_DIR`` and the reader accepts it.
* ``propose``, ``execute``, ``approve``, and ``complete_safe`` do not
  import ``fulfill`` or ``stripe``.
* An expired entitlement file still returns Echo-limited.
* README does not claim a live shop.
* README Author paragraph is untouched.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path


class TestT173FulfillOutsideCore(unittest.TestCase):
    """T173 — local fulfill is grant-gated and outside execute."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_FULFILL_GRANT", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY_FILE", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_FULFILL_GRANT", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY_FILE", None)

    # ── 1) Wrong or empty grant writes nothing ──

    def test_wrong_grant_writes_nothing(self) -> None:
        """A wrong or empty grant returns refused and writes no file."""
        os.environ["AEGIS_FULFILL_GRANT"] = "correct-grant"
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = "test-key-1234567890"
        from app.licensing.fulfill import fulfill_local

        result = fulfill_local("t1", "professional", 30, "wrong-grant")
        self.assertEqual(result["fulfill_state"], "refused")
        self.assertEqual(result["reason"], "wrong_grant")
        ent = Path(self._tmp) / "entitlement.json"
        self.assertFalse(ent.exists())

    def test_empty_grant_writes_nothing(self) -> None:
        """An empty grant string returns refused and writes no file."""
        os.environ["AEGIS_FULFILL_GRANT"] = "correct-grant"
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = "test-key-1234567890"
        from app.licensing.fulfill import fulfill_local

        result = fulfill_local("t1", "professional", 30, "")
        self.assertEqual(result["fulfill_state"], "refused")
        ent = Path(self._tmp) / "entitlement.json"
        self.assertFalse(ent.exists())

    # ── 2) Missing issuer key writes nothing ──

    def test_missing_key_writes_nothing(self) -> None:
        """A valid grant but missing key returns refused and writes no file."""
        os.environ["AEGIS_FULFILL_GRANT"] = "correct-grant"
        from app.licensing.fulfill import fulfill_local

        result = fulfill_local("t1", "professional", 30, "correct-grant")
        self.assertEqual(result["fulfill_state"], "refused")
        self.assertEqual(result["reason"], "missing_key")
        ent = Path(self._tmp) / "entitlement.json"
        self.assertFalse(ent.exists())

    # ── 3) Valid grant + key writes signed entitlement under tmp ──

    def test_valid_grant_writes_signed_entitlement_under_tmp(self) -> None:
        """A valid grant + key writes a signed entitlement.json under AEGIS_DATA_DIR."""
        os.environ["AEGIS_FULFILL_GRANT"] = "correct-grant"
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = "test-key-1234567890"
        from app.licensing.fulfill import fulfill_local

        result = fulfill_local("t1", "professional", 30, "correct-grant")
        self.assertEqual(result["fulfill_state"], "fulfilled")
        ent = Path(self._tmp) / "entitlement.json"
        self.assertTrue(ent.exists())
        data = json.loads(ent.read_text())
        self.assertEqual(data["tier"], "professional")
        self.assertEqual(data["tenant_id"], "t1")
        self.assertEqual(data.get("issuer"), "local-cli")
        self.assertIn("signature_sha256", data)

        # The reader must accept it when the key env is present.
        from core.entitlement import load

        loaded = load(tenant_id="t1")
        self.assertEqual(loaded["tier"], "professional")
        self.assertNotIn("reason", loaded)

    # ── 4) Propose / execute / approve / complete_safe do not import fulfill ──

    def test_execute_propose_do_not_import_fulfill_or_stripe(self) -> None:
        """core.twin_actions and core.llm_safety must not import fulfill or stripe."""
        import sys

        import core.llm_safety
        import core.twin_actions

        self.assertNotIn("stripe", sys.modules)

        import inspect

        twin_src = inspect.getsource(core.twin_actions)
        self.assertNotIn("fulfill", twin_src.lower())
        self.assertNotIn("stripe", twin_src.lower())

        safety_src = inspect.getsource(core.llm_safety)
        self.assertNotIn("fulfill", safety_src.lower())
        self.assertNotIn("stripe", safety_src.lower())

    # ── 5) Expired file still Echo-limited ──

    def test_expired_file_still_echo_limited(self) -> None:
        """An expired entitlement file still returns Echo-limited."""
        os.environ["AEGIS_FULFILL_GRANT"] = "correct-grant"
        os.environ["AEGIS_ENTITLEMENT_ISSUER_KEY"] = "test-key-1234567890"
        from app.licensing.fulfill import fulfill_local

        # Issue with 0 days so it's already expired.
        result = fulfill_local("t1", "professional", 0, "correct-grant")
        self.assertEqual(result["fulfill_state"], "fulfilled")
        from core.entitlement import load

        loaded = load(tenant_id="t1")
        self.assertEqual(loaded["tier"], "echo")
        self.assertEqual(loaded["reason"], "expired")

    # ── 6) README does not claim live shop ──

    def test_readme_does_not_claim_live_shop(self) -> None:
        """README Now section must not claim a live Stripe shop is deployed."""
        readme = Path("README.md").read_text(encoding="utf-8")
        now_section = (
            readme.split("## Now")[1].split("---")[0] if "## Now" in readme else ""
        )
        self.assertNotIn("live shop is deployed", now_section.lower())
        self.assertNotIn("live stripe shop", now_section.lower())

    # ── 7) README Author paragraph untouched ──

    def test_readme_author_untouched(self) -> None:
        """The Author paragraph must still mention Amin Azimi and the lab."""
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("Amin Azimi", readme)
        self.assertIn("Azimi Innovation Lab", readme)


if __name__ == "__main__":
    unittest.main()
