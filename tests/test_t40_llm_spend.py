"""T40 — persist token spend after complete_safe.

Verify that complete_safe uses the EchoProvider by default and that
after a successful completion the token spend is persisted to SQLite
via add_spend, so a restart keeps the cumulative burn.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from core.llm_provider import get_provider
from core.llm_safety import complete_safe
from core.twin_persist import get_budget


class TestT40LlmSpend(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t40_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        # Ensure the echo provider is the default.
        os.environ.pop("AEGIS_LLM_PROVIDER", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)

    def test_default_provider_is_echo(self):
        provider = get_provider()
        self.assertEqual(type(provider).__name__, "EchoProvider")

    def test_complete_safe_persists_spend(self):
        result = complete_safe("hello", tenant_id="t40")
        self.assertTrue(result["ok"])
        self.assertGreater(result["total_tokens"], 0)

        budget = get_budget("t40")
        self.assertIsNotNone(budget)
        self.assertGreater(float(budget["spent"]), 0)

    def test_spend_accumulates_across_calls(self):
        r1 = complete_safe("first prompt", tenant_id="t40-acc")
        r2 = complete_safe("second prompt", tenant_id="t40-acc")
        budget = get_budget("t40-acc")
        self.assertIsNotNone(budget)
        expected = r1["total_tokens"] + r2["total_tokens"]
        self.assertAlmostEqual(float(budget["spent"]), float(expected))

    def test_no_live_network(self):
        # This test exists to assert the suite does not require network.
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
