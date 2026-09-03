from __future__ import annotations

from core.agent_base import BaseAgent


class AminAgent(BaseAgent):
    """Finance and executive bridge specialist."""

    name = "Amin"
    role = "Finance and executive bridge"
    description = (
        "Provides secondary authority, review checkpoints, and governance "
        "coverage for finance flows, invoicing, and executive directives."
    )
    capabilities = ["finance", "invoicing", "settlement", "executive", "oversight", "audit"]
    metadata = {
        "log": {
            "channel": "oversight",
            "level": "info",
            "owner": "Amin Azimi",
            "component": "amin",
            "scope": "governance",
        },
        "execution": {
            "mode": "async",
            "telemetry": "enabled",
            "checkpoint": "review",
        },
    }

    def handle(self, task: str) -> str:
        return (
            f"{self.name} review: confirm the oversight checkpoint, audit "
            f"the financial path, settle the token budget, and validate "
            f"readiness for {task}"
        )
