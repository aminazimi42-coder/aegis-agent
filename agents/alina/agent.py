from __future__ import annotations

from core.agent_base import BaseAgent


class AlinaAgent(BaseAgent):
    """Strategic orchestration specialist."""

    name = "Alina"
    role = "Strategic coordination"
    description = "Coordinates strategy, prioritization, and system-level routing."
    capabilities = ["planning", "coordination", "routing", "prioritization"]

    def _propose_body(self, text: str) -> str:
        return f"Strategy: priority order for the ask — {text}"

    def handle(self, task: str) -> str:
        return (
            f"{self.name} strategic coordination: define a clear execution "
            f"strategy, route priorities, and align stakeholders for {task}"
        )
