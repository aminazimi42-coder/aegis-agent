"""T78 — AEGIS_OFFLINE flag forces Echo provider (offline mode)."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from core.llm_provider import EchoProvider, HttpProvider, get_provider
from core.twin_local_view import offline_mode


class OfflineModeEnvTest(unittest.TestCase):
    """offline_mode() reads AEGIS_OFFLINE correctly."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_OFFLINE", None)

    def test_offline_mode_reads_env_truthy(self) -> None:
        """1, true, yes (case-insensitive) → True."""
        for val in ("1", "true", "True", "TRUE", "yes", "Yes", "YES"):
            with patch.dict(os.environ, {"AEGIS_OFFLINE": val}):
                self.assertTrue(offline_mode(), msg=f"AEGIS_OFFLINE={val!r}")

    def test_offline_mode_reads_env_falsy(self) -> None:
        """0, false, no, empty, random string → False."""
        for val in ("0", "false", "no", "", "maybe"):
            with patch.dict(os.environ, {"AEGIS_OFFLINE": val}):
                self.assertFalse(offline_mode(), msg=f"AEGIS_OFFLINE={val!r}")

    def test_offline_mode_unset(self) -> None:
        """Unset → False."""
        os.environ.pop("AEGIS_OFFLINE", None)
        self.assertFalse(offline_mode())


class OfflineForcesEchoTest(unittest.TestCase):
    """When offline_mode() is True, get_provider() returns EchoProvider."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_OFFLINE", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)

    def test_offline_forces_echo_provider(self) -> None:
        """Even with AEGIS_LLM_PROVIDER=http, offline → EchoProvider."""
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "https://example.invalid/v1"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key"
        os.environ["AEGIS_OFFLINE"] = "1"
        provider = get_provider()
        self.assertIsInstance(provider, EchoProvider)

    def test_online_http_provider_still_used(self) -> None:
        """Without offline flag, http provider is returned (sanity)."""
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "https://example.invalid/v1"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key"
        os.environ.pop("AEGIS_OFFLINE", None)
        provider = get_provider()
        self.assertIsInstance(provider, HttpProvider)


if __name__ == "__main__":
    unittest.main()
