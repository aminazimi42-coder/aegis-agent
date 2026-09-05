"""T17 — Twin speech policy and budget stop.

Verifies:
- complete_safe after monkeypatch returning "payment sent to vendor"
  -> ok False and "rejected" in text.
- With AEGIS_LLM_BUDGET_EXHAUSTED=1, complete_safe does not call the
  provider; ok False and "budget" in text.lower().
- T15 wire_transfer still rejected (regression).
- AEGIS_DATA_DIR temp; no live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from core import llm_safety
from core.llm_safety import complete_safe


class FakeProvider:
    """Provider that returns a fixed text for testing speech policy."""

    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, prompt: str, *, model: str, max_tokens: int) -> dict:
        return {
            "text": self._text,
            "model": model,
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        }


class TestT17LLMPolicy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_LLM_BUDGET_EXHAUSTED", None)

    def tearDown(self):
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_BUDGET_EXHAUSTED", None)

    def test_forbidden_claim_rejected(self):
        """Monkeypatch provider returning 'payment sent to vendor' -> ok False."""
        from core.twin_quota import set_quota

        set_quota("t17", remaining=10, period_end="2099-12-31")
        fake = FakeProvider("payment sent to vendor")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake):
            result = complete_safe("send payment", tenant_id="t17")
        self.assertFalse(result["ok"])
        self.assertIn("rejected", result["text"].lower())

    def test_budget_exhausted_no_provider(self):
        """With AEGIS_LLM_BUDGET_EXHAUSTED=1, complete_safe does not call provider."""
        os.environ["AEGIS_LLM_BUDGET_EXHAUSTED"] = "1"

        class ExplodingProvider:
            def complete(self, *a, **kw):
                raise AssertionError("provider should not be called")

        with mock.patch.object(
            llm_safety, "get_provider", return_value=ExplodingProvider()
        ):
            result = complete_safe("hi", tenant_id="t17")
        self.assertFalse(result["ok"])
        self.assertIn("budget", result["text"].lower())

    def test_t15_wire_transfer_still_rejected(self):
        """Regression: T15 wire_transfer tool rejection still works."""
        from core.twin_quota import set_quota

        set_quota("t17", remaining=10, period_end="2099-12-31")
        fake = FakeProvider("TOOL:wire_transfer\nPAY")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake):
            result = complete_safe("transfer funds", tenant_id="t17")
        self.assertFalse(result["ok"])
        self.assertEqual(result["tool"], "wire_transfer")
        self.assertIn("rejected", result["text"].lower())


if __name__ == "__main__":
    unittest.main()
