from __future__ import annotations

from core.agent_base import BaseAgent


class BitaAgent(BaseAgent):
    """Analysis and synthesis specialist."""

    name = "Bita"

    def handle(self, task: str) -> str:
        return f"{self.name} analysis and synthesis: Evaluate the context, synthesize insight, and summarize the key risks for {task}"
