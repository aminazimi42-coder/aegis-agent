from __future__ import annotations

from core.agent_base import BaseAgent


class AylinAgent(BaseAgent):
    """Quality assurance and verification specialist."""

    name = "Aylin"
    role = "Quality and validation"
    description = "Validates quality, audits outcomes, and enforces final assurance."
    capabilities = ["validation", "quality", "audit", "assurance"]

    def _propose_body(self, text: str) -> str:
        return f"Quality: what would make the output fail review — {text}"

    def handle(self, task: str) -> str:
        return (
            f"{self.name} validation and quality review: check compliance, "
            f"verify the final outcome, and confirm the release-ready result "
            f"for {task}"
        )
