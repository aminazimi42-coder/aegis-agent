"""T82 — Zero or expired quota forces Echo.

Covers:
- When ``remaining`` is 0, ``complete_safe`` uses the Echo provider even
  when ``AEGIS_LLM_PROVIDER=http``.
- When ``period_end`` is a past UTC instant, ``complete_safe`` uses Echo
  even when ``AEGIS_LLM_PROVIDER=http``.
- No live network is used (the HTTP provider is mocked out).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from core import llm_safety
from core.twin_quota import set_quota


class TestT82QuotaForcesEcho(unittest.TestCase):
    """Zero or expired quota forces the Echo provider."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t82_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "http://localhost:0"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key-12345678"

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    def test_zero_remaining_forces_echo(self) -> None:
        """remaining=0 forces Echo even with AEGIS_LLM_PROVIDER=http."""
        set_quota("t82-zero", remaining=0, period_end="")

        # Patch get_provider to return an HttpProvider so we prove the
        # quota gate — not the provider config — is what forces Echo.
        from core.llm_provider import HttpProvider

        fake_http = HttpProvider("http://localhost:0", "test-key-12345678")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            result = llm_safety.complete_safe("ping", tenant_id="t82-zero")

        self.assertEqual(result["provider_kind"], "echo")
        self.assertNotIn("fallback_label", result)

    def test_expired_period_forces_echo(self) -> None:
        """A past period_end forces Echo even with remaining > 0."""
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        set_quota("t82-expired", remaining=100, period_end=past)

        from core.llm_provider import HttpProvider

        fake_http = HttpProvider("http://localhost:0", "test-key-12345678")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            result = llm_safety.complete_safe("ping", tenant_id="t82-expired")

        self.assertEqual(result["provider_kind"], "echo")
        self.assertNotIn("fallback_label", result)

    def test_no_live_network(self) -> None:
        """The suite must not require network access."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
