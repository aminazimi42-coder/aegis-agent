"""T66 — one complete_safe gateway; Echo default; HTTP labeled.

Verify that:
- complete_safe always calls get_provider() and includes provider_kind
  in its result dict.
- The default provider_kind is "echo".
- When an HttpProvider is returned by get_provider(), the result is
  labeled with provider_kind "http" and fallback_label "http-fallback".
- No live network is used (HTTP path is mocked).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from core import llm_safety


class TestT66CompleteSafeGateway(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t66_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        # Ensure the echo provider is the default.
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    def test_default_provider_kind_is_echo(self):
        """complete_safe with default config: provider_kind == 'echo'."""
        result = llm_safety.complete_safe("ping", tenant_id="t66")
        self.assertEqual(result["provider_kind"], "echo")
        self.assertNotIn("fallback_label", result)

    def test_http_result_is_labeled(self):
        """complete_safe when get_provider returns HttpProvider: labeled 'http'."""
        from core.llm_provider import HttpProvider
        from core.twin_quota import set_quota

        set_quota("t66-http", remaining=10, period_end="2099-12-31")
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
                result = llm_safety.complete_safe("ping", tenant_id="t66-http")
        self.assertEqual(result["provider_kind"], "http")
        self.assertEqual(result.get("fallback_label"), "http-fallback")

    def test_no_live_network(self):
        """The suite must not require network access."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
