from __future__ import annotations

from core.agent_base import BaseAgent


class KiyanAgent(BaseAgent):
    """Execution-focused specialist."""

    name = "Kiyan"

    def handle(self, task: str) -> str:
        return f"{self.name} executed: {task}"
