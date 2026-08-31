from __future__ import annotations

from typing import Any, Dict

from agents.alina.agent import AlinaAgent
from agents.aylin.agent import AylinAgent
from agents.bita.agent import BitaAgent
from agents.kiyan.agent import KiyanAgent
from core.agent_registry import AGENT_REGISTRY


class AICore:
    """Core coordination layer for routing tasks to the correct agent."""

    def __init__(self) -> None:
        self.registry = {agent.name: agent for agent in AGENT_REGISTRY}
        self.agent_map = {
            "Alina": AlinaAgent(),
            "Kiyan": KiyanAgent(),
            "Bita": BitaAgent(),
            "Aylin": AylinAgent(),
        }

    def resolve_agent_name(self, task: str) -> str:
        """Select the most appropriate agent for a given task string."""
        lower_task = task.lower()

        if any(keyword in lower_task for keyword in ["plan", "strategy", "coordinate", "prioritize", "route"]):
            return "Alina"
        if any(keyword in lower_task for keyword in ["execute", "deploy", "run", "operate", "monitor", "optimize"]):
            return "Kiyan"
        if any(keyword in lower_task for keyword in ["analyze", "reason", "synthesize", "summarize", "risk", "insight"]):
            return "Bita"
        if any(keyword in lower_task for keyword in ["validate", "verify", "check", "quality", "audit", "test"]):
            return "Aylin"
        return "Alina"

    def dispatch(self, task: str) -> Dict[str, Any]:
        """Dispatch a task to a specialist and return the result payload."""
        agent_name = self.resolve_agent_name(task)
        agent = self.agent_map[agent_name]
        response = agent.handle(task)

        return {
            "agent_name": agent_name,
            "response": response,
            "task": task,
        }
