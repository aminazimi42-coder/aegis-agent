"""LLM provider interface with a deterministic offline Echo provider."""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM completion providers."""

    name: str

    def is_available(self) -> bool:
        """Return True when the provider is ready to serve completions."""
        ...

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

    name: str = "echo"

    def is_available(self) -> bool:
        """Echo is always available."""
        return True

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

    name: str = "http"

    #: Default request timeout (seconds).  Override via the
    #: ``AEGIS_HTTP_TIMEOUT`` env var or the *timeout* constructor arg.
    DEFAULT_TIMEOUT: float = 8.0

    def __init__(self, base_url: str, api_key: str, timeout: float | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._last_probe_ok: bool = True
        if timeout is not None:
            self._timeout = float(timeout)
        else:
            import os as _os

            raw = _os.getenv("AEGIS_HTTP_TIMEOUT", "")
            try:
                self._timeout = float(raw) if raw else self.DEFAULT_TIMEOUT
            except (TypeError, ValueError):
                self._timeout = self.DEFAULT_TIMEOUT

    def is_available(self) -> bool:
        """Return False when base URL is missing or the last probe failed.

        The env-flag check is handled by :func:`get_provider`, which does not
        return an :class:`HttpProvider` when the flag is off.  This method
        covers the remaining cases: empty base URL or a previously failed
        probe.
        """
        if not self.base_url:
            return False
        return self._last_probe_ok

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
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (OSError, ValueError, RuntimeError):
            self._last_probe_ok = False
            return EchoProvider().complete(
                prompt, model=model, max_tokens=max_tokens,
            )
        self._last_probe_ok = True
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


def load_llm_key() -> str | None:
    """Load the LLM API key from the Keychain/mock, env, or the data-dir file.

    T196 — lookup order for the optional HTTP adapter token:

    1.  macOS Keychain (or mock on CI) via
        :func:`core.llm_keychain.load_optional_llm_key`,
    2.  ``AEGIS_LLM_API_KEY`` env (checked inside the keychain helper),
    3.  ``$AEGIS_DATA_DIR/llm_key`` file,
    4.  ``None``.

    This function never writes or creates the file — it only reads.
    """
    key = None
    try:
        from core.llm_keychain import load_optional_llm_key

        key = load_optional_llm_key()
    except Exception:
        pass
    if key and key.strip():
        return key.strip()
    key = os.getenv("AEGIS_LLM_API_KEY")
    if key and key.strip():
        return key.strip()
    from core.twin_local_view import data_root

    key_path = data_root() / "llm_key"
    if key_path.is_file():
        try:
            raw = key_path.read_text(encoding="utf-8").strip()
            if raw:
                return raw
        except OSError:
            pass
    return None


def http_requested() -> bool:
    """Return True when the HTTP provider path was requested (and not offline)."""
    from core.twin_local_view import offline_mode

    if offline_mode():
        return False
    kind = os.getenv("AEGIS_LLM_PROVIDER", "echo").lower()
    if kind == "echo":
        backend = os.getenv("AGENT_LLM_BACKEND", "").lower()
        if backend == "ollama":
            kind = "http"
    return kind == "http"


def get_provider() -> LLMProvider:
    """Return the configured LLM provider. Defaults to EchoProvider.

    When :func:`core.twin_local_view.offline_mode` is True the Echo
    provider is always returned, even when ``AEGIS_LLM_PROVIDER`` is
    ``http``.

    T157 — the API key is loaded from ``AEGIS_LLM_API_KEY`` or
    ``$AEGIS_DATA_DIR/llm_key`` via :func:`load_llm_key`.  When both
    are missing, ``HttpProvider`` is not constructed and EchoProvider
    is returned — no socket is opened.
    """
    if http_requested():
        base_url = os.getenv("AEGIS_LLM_BASE_URL")
        api_key = load_llm_key()
        if base_url and api_key:
            return HttpProvider(base_url, api_key)
    return EchoProvider()


def engine_label() -> str:
    """Return the honest operator engine label for the status surface.

    T194 — one English line sourced from the existing adapter contract:

    - ``"Echo"`` — default (no base URL, unset backend).
    - ``"HTTP (Ollama alias)"`` — ``AGENT_LLM_BACKEND=ollama`` and a
      reachable base URL is set.
    - ``"Echo (fallback)"`` — a base URL was set but the provider is
      unreachable (connection refused, 401, 500, timeout).

    Missing base URL, unset backend, connection refused, 401, 500, or
    timeout stays Echo (fallback) when a URL was set, else Echo.
    """
    base_url = os.getenv("AEGIS_LLM_BASE_URL", "").strip()

    if not base_url:
        return "Echo"

    # A base URL was set — check whether the provider is reachable.
    provider = get_provider()
    if isinstance(provider, HttpProvider) and provider.is_available():
        return "HTTP (Ollama alias)"
    return "Echo (fallback)"
