from __future__ import annotations

from core.agent_base import BaseAgent


class BitaAgent(BaseAgent):
    """Analysis and synthesis specialist."""

    name = "Bita"
    role = "Analysis and synthesis"
    description = "Evaluates context and turns it into high-quality decision insight."
    capabilities = ["analysis", "synthesis", "risk", "reporting"]

    def handle(self, task: str) -> str:
        return (
            f"{self.name} analysis and synthesis: evaluate the context, "
            f"synthesize insight, clarify the dependencies, and summarize "
            f"the key risks for {task}"
        )
