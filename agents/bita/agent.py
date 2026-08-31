from __future__ import annotations


class BitaAgent:
    """Analysis and synthesis specialist."""

    name = "Bita"

    def handle(self, task: str) -> str:
        return f"{self.name} analyzed: {task}"
