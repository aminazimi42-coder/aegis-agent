"""Optional LLM token backed by the macOS Keychain on Darwin.

T196 — an optional LLM credential may live in the macOS Keychain instead of
a committed env file or a data-dir file.  On non-Darwin hosts (CI) a mock
in-memory store is used so tests never require a real Keychain.

The lookup order for the optional HTTP adapter token is:

1.  Keychain/mock store value (when present),
2.  ``AGENT_LLM_API_KEY`` env var (when set),
3.  no token (``None``).

No token + no base URL → Echo.  No token + a base URL → the existing labeled
HTTP path that 401-falls-back to Echo as T136.

This module never writes the token into README, STATUS, receipts, audit
JSONL, operator HTML, session receipt, SQLite, or fixtures.

The service name is ``AegisOperator`` and the account is ``llm-token``.
"""

from __future__ import annotations

import os
import platform
from typing import Protocol

SERVICE_NAME = "AegisOperator"
ACCOUNT_NAME = "llm-token"


class _KeychainStore(Protocol):
    """Minimal protocol for a keychain store (real or mock)."""

    def get(self, service: str, account: str) -> str | None:
        ...

    def set(self, service: str, account: str, value: str) -> None:
        ...


# --------------------------------------------------------------------------- #
# Darwin Keychain backed by the system ``security`` CLI
# --------------------------------------------------------------------------- #


class DarwinKeychain:
    """Thin wrapper around the macOS ``security`` CLI.

    No payment keys are stored here — only the optional LLM token.  The
    secret value is never printed or logged by this class.
    """

    def get(self, service: str, account: str) -> str | None:
        """Return the stored secret, or ``None`` when not found."""
        import subprocess

        try:
            result = subprocess.run(
                [
                    "/usr/bin/security",
                    "find-generic-password",
                    "-s",
                    service,
                    "-a",
                    account,
                    "-w",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def set(self, service: str, account: str, value: str) -> None:
        """Store a secret in the Keychain."""
        import subprocess

        subprocess.run(
            [
                "/usr/bin/security",
                "add-generic-password",
                "-s",
                service,
                "-a",
                account,
                "-w",
                value,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )


# --------------------------------------------------------------------------- #
# Mock store for non-Darwin / CI
# --------------------------------------------------------------------------- #


class MockKeychain:
    """In-memory mock store used on non-Darwin hosts and in tests."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get(self, service: str, account: str) -> str | None:
        return self._store.get((service, account))

    def set(self, service: str, account: str, value: str) -> None:
        self._store[(service, account)] = value


# --------------------------------------------------------------------------- #
# Store selection
# --------------------------------------------------------------------------- #


def _is_darwin() -> bool:
    """Return True on macOS."""
    return platform.system() == "Darwin"


def get_store() -> _KeychainStore:
    """Return the active keychain store.

    On Darwin the real Keychain is used; on all other platforms a mock
    in-memory store is returned so tests and CI never require a Keychain.
    """
    if _is_darwin():
        return DarwinKeychain()
    return MockKeychain()


# --------------------------------------------------------------------------- #
# Token lookup
# --------------------------------------------------------------------------- #


def load_llm_token_from_keychain() -> str | None:
    """Return the optional LLM token from the Keychain/mock store.

    Returns ``None`` when the store has no value for the configured
    service/account pair.  The token is never printed or logged.
    """
    store = get_store()
    value = store.get(SERVICE_NAME, ACCOUNT_NAME)
    if value and value.strip():
        return value.strip()
    return None


def load_optional_llm_key() -> str | None:
    """Resolve the optional LLM API key with the T196 lookup order.

    Order:
    1.  Keychain/mock store value (when present),
    2.  ``AGENT_LLM_API_KEY`` env var (when set),
    3.  ``None``.
    """
    key = load_llm_token_from_keychain()
    if key:
        return key
    env_key = os.getenv("AGENT_LLM_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()
    return None
