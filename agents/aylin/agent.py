from __future__ import annotations

from core.agent_base import BaseAgent


class AylinAgent(BaseAgent):
    """Quality assurance and verification specialist."""

    name = "Aylin"
    role = "Quality and validation"
    description = "Validates quality, audits outcomes, and enforces final assurance."
    capabilities = ["validation", "quality", "audit", "assurance"]

    def handle(self, task: str) -> str:
        return f"{self.name} validation and quality review: check compliance, verify the final outcome, and confirm the release-ready result for {task}"
