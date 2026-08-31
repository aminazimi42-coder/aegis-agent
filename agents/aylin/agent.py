from __future__ import annotations

from core.agent_base import BaseAgent


class AylinAgent(BaseAgent):
    """Quality assurance and verification specialist."""

    name = "Aylin"

    def handle(self, task: str) -> str:
        return f"{self.name} validated: {task}"
