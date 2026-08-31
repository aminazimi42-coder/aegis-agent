from __future__ import annotations


class AlinaAgent:
    """Strategic orchestration specialist."""

    name = "Alina"

    def handle(self, task: str) -> str:
        return f"{self.name} coordinated: {task}"
