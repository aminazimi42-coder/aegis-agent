from __future__ import annotations

from abc import ABC, abstractmethod

from core.agent_registry import AGENT_REGISTRY


class BaseAgent(ABC):
    """Base abstraction for all specialist agents in the platform."""

    name: str = "BaseAgent"

    def profile(self) -> dict:
        """Return the canonical metadata for the agent."""
        for agent in AGENT_REGISTRY:
            if agent.name == self.name:
                return {
                    "name": agent.name,
                    "role": agent.role,
                    "description": agent.description,
                    "capabilities": agent.capabilities,
                }
        return {"name": self.name, "role": "Specialist", "description": "Unspecified specialist role.", "capabilities": []}

    @abstractmethod
    def handle(self, task: str) -> str:
        """Process a task and return a textual response."""
        raise NotImplementedError
