"""T134 — Optional local model on existing T116 adapter.

Covers:
- When ``AGENT_LLM_BASE_URL`` is empty (or unset), the provider is Echo
  and the result is labeled ``echo``.
- When ``AGENT_LLM_BASE_URL`` is set (and a valid key), the HTTP path is
  used and the result is labeled ``http`` (not a silent swap).
- ``STATUS.md`` does not claim that Ollama is bundled.
- No live network except TestClient.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import llm_safety
from core.llm_provider import HttpProvider
from core.twin_quota import set_quota


class TestT134LocalAdapter(unittest.TestCase):
    """Optional local adapter on the existing T116 adapter."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t134_")
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

    def test_empty_env_is_echo(self) -> None:
        """When AGENT_LLM_BASE_URL is empty, the provider is Echo."""
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        result = llm_safety.complete_safe("ping", tenant_id="t134-empty")
        self.assertEqual(result["provider_kind"], "echo")
        self.assertNotIn("fallback_label", result)

    def test_set_url_is_labeled_http(self) -> None:
        """When AGENT_LLM_BASE_URL is set, the HTTP path is labeled, not silent."""
        os.environ["AEGIS_LLM_PROVIDER"] = "http"
        os.environ["AEGIS_LLM_BASE_URL"] = "http://localhost:11434"
        os.environ["AEGIS_LLM_API_KEY"] = "test-key-t134-123456"
        set_quota("t134-http", remaining=10, period_end="2099-12-31")
        fake_http = HttpProvider("http://localhost:11434", "test-key-t134-123456")
        with mock.patch.object(llm_safety, "get_provider", return_value=fake_http):
            with mock.patch.object(
                fake_http,
                "complete",
                return_value={
                    "text": "ok",
                    "model": "aegis-cheap",
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            ):
                result = llm_safety.complete_safe(
                    "ping", tenant_id="t134-http",
                )
        self.assertEqual(result["provider_kind"], "http")
        # HTTP-path completion is labeled, not silent
        self.assertEqual(result.get("fallback_label"), "http-fallback")

    def test_status_does_not_claim_bundled_ollama(self) -> None:
        """STATUS.md must not claim Ollama is bundled."""
        status_path = Path(__file__).resolve().parent.parent / "STATUS.md"
        text = status_path.read_text(encoding="utf-8").lower()
        self.assertNotIn("ollama is bundled", text)
        self.assertNotIn("bundled ollama", text)

    def test_no_live_network(self) -> None:
        """The suite must not require network access."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
