from __future__ import annotations

from core.agent_registry import AGENT_REGISTRY


def orchestrate_platform() -> str:
    """Run the initial orchestration pass for the platform."""
    names = [agent.name for agent in AGENT_REGISTRY]
    return "Aegis platform initialized with agents: " + ", ".join(names)
