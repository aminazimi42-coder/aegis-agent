"""T09 — Paid-LLM adapter with Echo fallback.

Tests that:
- Default get_provider() returns EchoProvider.
- HttpProvider.complete returns remote text when urlopen succeeds (monkeypatched).
- HttpProvider.complete falls back to Echo on network error.
- No hardcoded API key in the module source.
- Env vars are isolated (setUp/tearDown).
- No live network is called.
"""

from __future__ import annotations

import io
import json
import os
from unittest import mock

import pytest
from core.llm_provider import HttpProvider, get_provider


class TestPaidLLMAdapter:
    """T09: HTTP LLM adapter with Echo fallback."""

    ENV_KEYS = (
        "AEGIS_LLM_PROVIDER",
        "AEGIS_LLM_BASE_URL",
        "AEGIS_LLM_API_KEY",
    )

    def setUp_env(self, **kwargs: str) -> None:
        """Set env vars for the current test (monkeypatch-safe)."""
        for key in self.ENV_KEYS:
            monkeypatch = pytest.MonkeyPatch()
            monkeypatch.delenv(key, raising=False)
        for key, val in kwargs.items():
            os.environ[key] = val

    def tearDown_env(self) -> None:
        """Clean env vars after each test."""
        for key in self.ENV_KEYS:
            os.environ.pop(key, None)

    def test_default_provider_is_echo(self) -> None:
        """get_provider() with no env returns EchoProvider."""
        self.setUp_env()
        try:
            provider = get_provider()
            assert type(provider).__name__ == "EchoProvider"
        finally:
            self.tearDown_env()

    def test_http_provider_returns_remote_text(self) -> None:
        """HttpProvider.complete returns remote text when urlopen succeeds."""
        self.setUp_env(
            AEGIS_LLM_PROVIDER="http",
            AEGIS_LLM_BASE_URL="https://fake.example.com",
            AEGIS_LLM_API_KEY="test-key-not-real",
        )
        try:
            fake_body = json.dumps({"text": "hello from remote"}).encode("utf-8")
            fake_resp = io.BytesIO(fake_body)

            with mock.patch("urllib.request.urlopen", return_value=fake_resp):
                provider = HttpProvider("https://fake.example.com", "test-key-not-real")
                result = provider.complete("hi", model="aegis-cheap", max_tokens=8)

            assert result["text"] == "hello from remote"
            assert not result["text"].startswith("ECHO[")
        finally:
            self.tearDown_env()

    def test_http_provider_falls_back_to_echo_on_oserror(self) -> None:
        """HttpProvider.complete falls back to Echo on OSError."""
        self.setUp_env(
            AEGIS_LLM_PROVIDER="http",
            AEGIS_LLM_BASE_URL="https://fake.example.com",
            AEGIS_LLM_API_KEY="test-key-not-real",
        )
        try:
            with mock.patch("urllib.request.urlopen", side_effect=OSError("network down")):
                provider = HttpProvider("https://fake.example.com", "test-key-not-real")
                result = provider.complete("hi", model="aegis-cheap", max_tokens=8)

            assert result["text"].startswith("ECHO[")
        finally:
            self.tearDown_env()

    def test_http_provider_falls_back_on_json_error(self) -> None:
        """HttpProvider.complete falls back to Echo on JSON parse error (ValueError)."""
        self.setUp_env(
            AEGIS_LLM_PROVIDER="http",
            AEGIS_LLM_BASE_URL="https://fake.example.com",
            AEGIS_LLM_API_KEY="test-key-not-real",
        )
        try:
            fake_body = b"not json at all"
            fake_resp = io.BytesIO(fake_body)

            with mock.patch("urllib.request.urlopen", return_value=fake_resp):
                provider = HttpProvider("https://fake.example.com", "test-key-not-real")
                result = provider.complete("hi", model="aegis-cheap", max_tokens=8)

            assert result["text"].startswith("ECHO[")
        finally:
            self.tearDown_env()

    def test_no_hardcoded_api_key_in_source(self) -> None:
        """Module source must not contain a hardcoded sk- key."""
        from pathlib import Path

        source = Path("core/llm_provider.py").read_text()
        assert "sk-" not in source, (
            "llm_provider.py must not contain a hardcoded sk- API key."
        )

    def test_openai_style_choices_response(self) -> None:
        """HttpProvider.complete accepts OpenAI-style body.choices[0].text."""
        self.setUp_env(
            AEGIS_LLM_PROVIDER="http",
            AEGIS_LLM_BASE_URL="https://fake.example.com",
            AEGIS_LLM_API_KEY="test-key-not-real",
        )
        try:
            fake_body = json.dumps(
                {"choices": [{"text": "openai-style response"}]}
            ).encode("utf-8")
            fake_resp = io.BytesIO(fake_body)

            with mock.patch("urllib.request.urlopen", return_value=fake_resp):
                provider = HttpProvider("https://fake.example.com", "test-key-not-real")
                result = provider.complete("hi", model="aegis-cheap", max_tokens=8)

            assert result["text"] == "openai-style response"
            assert not result["text"].startswith("ECHO[")
        finally:
            self.tearDown_env()
