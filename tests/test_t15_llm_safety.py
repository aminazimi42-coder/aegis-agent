"""T15 — LLM tool cage and structured complete.

Verifies:
- default complete_safe with Echo: ok True, tool "" or allowed.
- complete_safe after monkeypatching get_provider to return a text
  containing ``TOOL:wire_transfer`` -> ok False and "rejected" in text.
- core/llm_safety.py source does not call execute(.
- AEGIS_DATA_DIR temp isolation; no live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from core import llm_safety
from core.llm_safety import ALLOWED_TOOLS, complete_safe


class FakeProvider:
    """Provider that returns a fixed text for testing tool rejection."""

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


class TestT15LLMSafety(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self):
        os.environ.pop("AEGIS_DATA_DIR", None)

    def test_default_complete_safe_ok(self):
        """Default complete_safe with Echo: ok True, tool '' or allowed."""
        result = complete_safe("hello", tenant_id="t15")
        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "aegis-cheap")
        # tool is either "" or an allowed tool
        self.assertIn(result["tool"], ("", *ALLOWED_TOOLS))

    def test_rejected_tool_not_allowed(self):
        """complete_safe after monkeypatch returning TOOL:wire_transfer -> ok False."""
        from core.twin_quota import set_quota

        set_quota("t15", remaining=10, period_end="2099-12-31")
        fake = FakeProvider("TOOL:wire_transfer\nPAY")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake):
            result = complete_safe("transfer funds", tenant_id="t15")
        self.assertFalse(result["ok"])
        self.assertEqual(result["tool"], "wire_transfer")
        self.assertIn("rejected", result["text"].lower())

    def test_source_does_not_call_execute(self):
        """core/llm_safety.py source does not call execute(."""
        import pathlib

        source = pathlib.Path(llm_safety.__file__).read_text()
        # Check that there is no call to execute(
        self.assertNotIn("execute(", source)
        # Also check we never import twin_actions
        self.assertNotIn("twin_actions", source)


if __name__ == "__main__":
    unittest.main()
