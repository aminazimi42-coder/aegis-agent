from __future__ import annotations

from core.recovery.self_recovery import RecoveryOutcome, SelfRecovery
from core.runtime.runtime_context import RuntimeContext


class RuntimeService:
    """Provides startup validation and recovery logic for environment consistency."""

    def __init__(self, context: RuntimeContext):
        self.context = context
        self.recovery = SelfRecovery(context.environment, context.agent_count)

    def bootstrap(self) -> dict:
        """Runs bootstrap-level verification before the runtime starts."""
        outcome: RecoveryOutcome = self.recovery.reconcile(
            expected_environment=self.context.environment
        )

        return {
            "service": self.context.app_name,
            "environment": self.context.environment,
            "status": "healthy" if outcome["reconciled"] else "stabilizing",
            "actions": outcome["actions"],
            "runtime": outcome["runtime"],
        }
