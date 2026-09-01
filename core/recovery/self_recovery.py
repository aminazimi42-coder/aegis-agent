from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class RecoveryOutcome(TypedDict):
    """Deterministic recovery summary for deployment alignment."""

    reconciled: bool
    actions: List[str]
    runtime: Dict[str, Any]


class SelfRecovery:
    """Normalizes local development artifacts to production-safe runtime settings."""

    VALID_ENVIRONMENTS = {"development", "staging", "production"}

    def __init__(self, environment: str, agent_count: int):
        self.environment = environment if environment in self.VALID_ENVIRONMENTS else "development"
        self.agent_count = agent_count

    def normalize_environment(self, expected_environment: str | None = None) -> str:
        """Coerce runtime state into a valid deployment environment."""
        target = expected_environment or self.environment
        if target not in self.VALID_ENVIRONMENTS:
            return "development"
        return target

    def reconcile(self, expected_environment: str | None = None) -> RecoveryOutcome:
        """Run a self-diagnostic recovery routine before runtime activation."""
        normalized_environment = self.normalize_environment(expected_environment)
        actions: List[str] = []

        if self.environment != normalized_environment:
            actions.append(
                "Normalized runtime environment from "
                f"{self.environment} to {normalized_environment}."
            )

        if self.agent_count != 4:
            actions.append("Adjusted agent count to the production-safe default of four agents.")
            runtime_agent_count = 4
        else:
            runtime_agent_count = self.agent_count

        if not actions:
            actions.append("Runtime configuration already matches production-safe defaults.")

        return {
            "reconciled": True,
            "actions": actions,
            "runtime": {
                "environment": normalized_environment,
                "agent_count": runtime_agent_count,
                "deployment_mode": "production-safe",
            },
        }
