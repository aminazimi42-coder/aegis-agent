"""Honest platform status surface for the Aegis Agent platform.

Returns a plain, verifiable snapshot of the platform's runtime
configuration — no marketing claims, no inflated language.

Keys:
  - version:          from config (1.0.0-rc1)
  - agent_count:      6
  - agents:           six agent names in registry order
  - llm_provider:     class name of the active provider (Echo/Http)
                      or ``AEGIS_LLM_PROVIDER`` default
  - twin_routes:       True if twin modules import cleanly
  - persistence:       "sqlite"
"""

from __future__ import annotations

import time

from core.agent_registry import AGENT_REGISTRY
from core.config import load_config
from core.llm_provider import HttpProvider, get_provider

_PROCESS_START: float = time.monotonic()


def _twin_routes_available() -> bool:
    """Return True if all twin modules import without error."""
    try:
        import core.twin_actions  # noqa: F401
        import core.twin_events  # noqa: F401
        import core.twin_git_observer  # noqa: F401
        import core.twin_interview  # noqa: F401

        return True
    except Exception:
        return False


def _http_token_cost() -> int:
    """Return the cumulative HTTP token cost as an integer.

    On Echo (the default provider) this is always 0 — no paid LLM is
    wired.  When an :class:`HttpProvider` is active the cost is the
    total tokens from the last completion, read from the twin_persist
    spend ledger.  No cloud billing is invented.
    """
    provider = get_provider()
    if not isinstance(provider, HttpProvider):
        return 0
    try:
        from core.twin_persist import get_budget

        budget = get_budget("aegis-status")
        if budget is None:
            return 0
        return int(budget.get("spent", 0))
    except Exception:
        return 0


def platform_status() -> dict:
    """Return an honest, verifiable platform status dict."""
    from core.entitlement import current_tier

    config = load_config()
    provider = get_provider()
    duration_ms = int((time.monotonic() - _PROCESS_START) * 1000)
    from core.llm_provider import engine_label
    return {
        "version": config.version,
        "agent_count": len(AGENT_REGISTRY),
        "agents": [agent.name for agent in AGENT_REGISTRY],
        "llm_provider": type(provider).__name__,
        "engine": engine_label(),
        "twin_routes": _twin_routes_available(),
        "persistence": "sqlite",
        "tier": current_tier(),
        "duration_ms": duration_ms,
        "http_token_cost": _http_token_cost(),
    }
