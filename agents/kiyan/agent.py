from __future__ import annotations


class KiyanAgent:
    """Execution-focused specialist."""

    name = "Kiyan"

    def handle(self, task: str) -> str:
        return f"{self.name} executed: {task}"
