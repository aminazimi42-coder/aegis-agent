from __future__ import annotations


class AylinAgent:
    """Quality assurance and verification specialist."""

    name = "Aylin"

    def handle(self, task: str) -> str:
        return f"{self.name} validated: {task}"
