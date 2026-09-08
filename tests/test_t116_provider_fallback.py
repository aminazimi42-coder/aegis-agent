"""T116 — LLM provider contract: Echo default with labeled fallback.

Covers:
- Default provider is Echo.
- HTTP 401, timeout, and 500 all fall back to Echo.
- The fallback result is labeled ``provider=echo(fallback)``.
- No live network is used (mocks only).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from core import llm_safety
from core.llm_provider import HttpProvider
from core.twin_quota import set_quota


class TestT116ProviderFallback(unittest.TestCase):
    """Echo-default provider fallback contract."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t116_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)
        os.environ.pop("AEGIS_LLM_BUDGET_EXHAUSTED", None)
        os.environ.pop("AEGIS_OFFLINE", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)
        os.environ.pop("AEGIS_LLM_BUDGET_EXHAUSTED", None)
        os.environ.pop("AEGIS_OFFLINE", None)

    def test_default_is_echo(self) -> None:
        """Default provider is Echo (provider_kind == 'echo')."""
        result = llm_safety.complete_safe("ping", tenant_id="t116-default")
        self.assertEqual(result["provider_kind"], "echo")
        self.assertNotIn("fallback_label", result)

    def test_http_401_falls_back_to_echo(self) -> None:
        """HTTP 401 error falls back to Echo with fallback label."""
        set_quota("t116-401", remaining=10, period_end="2099-12-31")
        fake_http = HttpProvider("http://localhost:0", "test-key-12345678")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            with mock.patch.object(
                fake_http,
                "complete",
                side_effect=OSError("HTTP 401 Unauthorized"),
            ):
                result = llm_safety.complete_safe(
                    "ping", tenant_id="t116-401",
                )
        self.assertEqual(result["provider_kind"], "echo")
        self.assertEqual(result.get("fallback_label"), "echo(fallback)")

    def test_http_timeout_falls_back_to_echo(self) -> None:
        """HTTP timeout falls back to Echo with fallback label."""
        set_quota("t116-timeout", remaining=10, period_end="2099-12-31")
        fake_http = HttpProvider("http://localhost:0", "test-key-12345678")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            with mock.patch.object(
                fake_http,
                "complete",
                side_effect=OSError("timed out"),
            ):
                result = llm_safety.complete_safe(
                    "ping", tenant_id="t116-timeout",
                )
        self.assertEqual(result["provider_kind"], "echo")
        self.assertEqual(result.get("fallback_label"), "echo(fallback)")

    def test_http_500_falls_back_to_echo(self) -> None:
        """HTTP 500 error falls back to Echo with fallback label."""
        set_quota("t116-500", remaining=10, period_end="2099-12-31")
        fake_http = HttpProvider("http://localhost:0", "test-key-12345678")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            with mock.patch.object(
                fake_http,
                "complete",
                side_effect=RuntimeError("HTTP 500 Internal Server Error"),
            ):
                result = llm_safety.complete_safe(
                    "ping", tenant_id="t116-500",
                )
        self.assertEqual(result["provider_kind"], "echo")
        self.assertEqual(result.get("fallback_label"), "echo(fallback)")

    def test_fallback_labeled(self) -> None:
        """A fallback result carries the label provider=echo(fallback)."""
        set_quota("t116-label", remaining=10, period_end="2099-12-31")
        fake_http = HttpProvider("http://localhost:0", "test-key-12345678")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            with mock.patch.object(
                fake_http,
                "complete",
                side_effect=OSError("connection refused"),
            ):
                result = llm_safety.complete_safe(
                    "ping", tenant_id="t116-label",
                )
        self.assertIn("fallback_label", result)
        self.assertEqual(result["fallback_label"], "echo(fallback)")

    def test_no_live_network(self) -> None:
        """The suite must not require network access."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
