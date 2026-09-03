from __future__ import annotations

from core.agent_base import BaseAgent


class AhmadAgent(BaseAgent):
    """Security and oversight specialist."""

    name = "Ahmad"
    role = "Security and oversight"
    description = (
        "Provides governance, stewardship, and oversight coverage "
        "for elevated authority workflows, KMS rotation, and incident triage."
    )
    capabilities = ["oversight", "governance", "review", "escalation", "security", "kms"]
    metadata = {
        "log": {
            "channel": "oversight",
            "level": "info",
            "owner": "Ahmad",
            "component": "ahmad",
            "scope": "governance",
        },
        "execution": {
            "mode": "async",
            "telemetry": "enabled",
            "checkpoint": "escalation",
        },
    }

    def handle(self, task: str) -> str:
        return (
            f"{self.name} governance: maintain the strategic oversight view, "
            f"rotate KMS keys, and confirm the authority path for {task}"
        )


# Backward-compatible alias
AhmedAgent = AhmadAgent
