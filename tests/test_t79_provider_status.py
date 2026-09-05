"""T79 — provider_status() reports Echo versus HTTP-fallback."""

from __future__ import annotations

import os
import tempfile
import unittest

from core.twin_local_view import provider_status


class ProviderStatusTest(unittest.TestCase):
    """provider_status() returns the correct kind and offline flag."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    def test_status_has_kind_key(self) -> None:
        """provider_status() returns a dict with a ``kind`` key."""
        status = provider_status()
        self.assertIn("kind", status)
        self.assertIn("offline", status)

    def test_status_echo_when_offline(self) -> None:
        """When offline_mode() is True, kind is ``echo``."""
        os.environ["AEGIS_OFFLINE"] = "1"
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "https://example.invalid/v1"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key"
        status = provider_status()
        self.assertEqual(status["kind"], "echo")
        self.assertTrue(status["offline"])

    def test_status_echo_when_no_http_configured(self) -> None:
        """Default env → echo, not http-fallback."""
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        status = provider_status()
        self.assertEqual(status["kind"], "echo")
        self.assertFalse(status["offline"])

    def test_status_http_fallback_when_http_configured(self) -> None:
        """When get_provider() returns HttpProvider and offline is False, kind is http-fallback."""
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "https://example.invalid/v1"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key"
        status = provider_status()
        self.assertEqual(status["kind"], "http-fallback")
        self.assertFalse(status["offline"])


if __name__ == "__main__":
    unittest.main()
