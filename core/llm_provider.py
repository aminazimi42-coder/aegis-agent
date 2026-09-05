"""LLM provider interface with a deterministic offline Echo provider."""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM completion providers."""

    def complete(
        self,
        prompt: str,
        *,
        model: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Return a completion dict with keys: text, model, prompt_tokens,
        completion_tokens, total_tokens.
        """
        ...


def _estimate_tokens(text: str) -> int:
    """Deterministic token estimate: max(1, len//4)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class EchoProvider:
    """Deterministic, no-network LLM provider for tests and offline CI."""

    def complete(
        self,
        prompt: str,
        *,
        model: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        snippet = prompt[:200]
        text = f"ECHO[{model}]: {snippet}"
        prompt_tokens = _estimate_tokens(prompt)
        completion_tokens = _estimate_tokens(text)
        return {
            "text": text,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }


class HttpProvider:
    """Optional HTTP-based LLM provider using stdlib urllib.

    Only activated when AEGIS_LLM_BASE_URL and AEGIS_LLM_API_KEY are both set.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def complete(
        self,
        prompt: str,
        *,
        model: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        import json
        import urllib.request

        payload = json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "max_tokens": max_tokens,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError, RuntimeError):
            return EchoProvider().complete(
                prompt, model=model, max_tokens=max_tokens,
            )
        # Accept OpenAI-style body.choices[0].text or plain body.text
        text = ""
        choices = body.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                text = first.get("text", "")
            elif isinstance(first, str):
                text = first
        if not text:
            text = body.get("text", "")
        return {
            "text": text,
            "model": model,
            "prompt_tokens": body.get("prompt_tokens", _estimate_tokens(prompt)),
            "completion_tokens": body.get(
                "completion_tokens", _estimate_tokens(text),
            ),
            "total_tokens": body.get(
                "total_tokens",
                _estimate_tokens(prompt) + _estimate_tokens(text),
            ),
        }


def get_provider() -> LLMProvider:
    """Return the configured LLM provider. Defaults to EchoProvider.

    When :func:`core.twin_local_view.offline_mode` is True the Echo
    provider is always returned, even when ``AEGIS_LLM_PROVIDER`` is
    ``http``.
    """
    from core.twin_local_view import offline_mode

    if offline_mode():
        return EchoProvider()
    kind = os.getenv("AEGIS_LLM_PROVIDER", "echo").lower()
    if kind == "http":
        base_url = os.getenv("AEGIS_LLM_BASE_URL")
        api_key = os.getenv("AEGIS_LLM_API_KEY")
        if base_url and api_key:
            return HttpProvider(base_url, api_key)
    return EchoProvider()
