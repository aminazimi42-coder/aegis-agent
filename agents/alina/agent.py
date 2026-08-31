from __future__ import annotations

from core.agent_base import BaseAgent


class AlinaAgent(BaseAgent):
    """Strategic orchestration specialist."""

    name = "Alina"

    def handle(self, task: str) -> str:
        return f"{self.name} coordinated: {task}"
