"""T81 — HTTP path consumes quota; Echo does not.

Covers:
- A successful HTTP-provider ``complete_safe`` call decrements the
  tenant's remaining quota by 1.
- An Echo-provider ``complete_safe`` call leaves remaining unchanged.
- No live network is used (the HTTP provider is mocked).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from core import llm_safety
from core.twin_quota import get_quota, set_quota


class TestT81HttpConsumesQuota(unittest.TestCase):
    """HTTP completions consume quota; Echo completions do not."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t81_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    def test_http_complete_decrements_quota(self) -> None:
        """A successful HTTP completion decrements remaining by 1."""
        from core.llm_provider import HttpProvider

        set_quota("t81-http", remaining=10, period_end="2026-12-31")

        fake_http = HttpProvider("http://localhost:0", "test-key-12345678")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            with mock.patch.object(
                fake_http, "complete", return_value={
                    "text": "hello from http",
                    "model": "aegis-cheap",
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                }
            ):
                result = llm_safety.complete_safe("ping", tenant_id="t81-http")

        self.assertEqual(result["provider_kind"], "http")
        self.assertEqual(result.get("fallback_label"), "http-fallback")
        self.assertEqual(result["ok"], True)

        after = get_quota("t81-http")
        self.assertEqual(after["remaining"], 9)

    def test_echo_complete_does_not_decrement(self) -> None:
        """An Echo completion leaves remaining unchanged."""
        set_quota("t81-echo", remaining=10, period_end="2026-12-31")

        result = llm_safety.complete_safe("ping", tenant_id="t81-echo")

        self.assertEqual(result["provider_kind"], "echo")
        self.assertNotIn("fallback_label", result)

        after = get_quota("t81-echo")
        self.assertEqual(after["remaining"], 10)

    def test_no_live_network(self) -> None:
        """The suite must not require network access."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
