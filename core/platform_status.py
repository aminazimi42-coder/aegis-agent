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

from core.agent_registry import AGENT_REGISTRY
from core.config import load_config
from core.llm_provider import get_provider


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


def platform_status() -> dict:
    """Return an honest, verifiable platform status dict."""
    config = load_config()
    provider = get_provider()
    return {
        "version": config.version,
        "agent_count": len(AGENT_REGISTRY),
        "agents": [agent.name for agent in AGENT_REGISTRY],
        "llm_provider": type(provider).__name__,
        "twin_routes": _twin_routes_available(),
        "persistence": "sqlite",
    }
