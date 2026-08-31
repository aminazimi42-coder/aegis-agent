from __future__ import annotations

from core.ai_core import AICore
from core.agent_registry import AGENT_REGISTRY


def orchestrate_platform() -> str:
    """Run the initial orchestration pass for the platform."""
    names = [agent.name for agent in AGENT_REGISTRY]
    return "Aegis platform initialized with agents: " + ", ".join(names)


def run_agent_workflow(task: str) -> dict:
    """Execute the AI coordination workflow for a single task."""
    ai_core = AICore()
    selected_result = ai_core.dispatch(task)

    return {
        "platform_name": "Aegis Agent Platform",
        "agent_count": len(AGENT_REGISTRY),
        "selected_agent": selected_result["agent_name"],
        "results": [selected_result],
    }
