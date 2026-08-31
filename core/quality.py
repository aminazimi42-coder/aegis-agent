from __future__ import annotations

from typing import Any, Dict

from core.security import SecurityPolicy


class ProductionQualityGate:
    """Enforce a strict runtime quality gate before task completion is accepted."""

    @staticmethod
    def evaluate(task: str, agent_name: str, response: str) -> Dict[str, Any]:
        policy = SecurityPolicy()
        checks = {
            "task_present": bool(task and str(task).strip()),
            "response_present": bool(response and str(response).strip()),
            "agent_allowed": policy.is_allowed(agent_name),
            "response_has_specialized_context": any(
                keyword in str(response).lower()
                for keyword in ["strategy", "execution", "analysis", "validation", "orchestration", "quality", "synthesis"]
            ),
        }
        passed = all(checks.values())
        return {
            "name": "production_quality_gate",
            "status": "passed" if passed else "failed",
            "passed": passed,
            "agent": agent_name,
            "checks": checks,
        }
