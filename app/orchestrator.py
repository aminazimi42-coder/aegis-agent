from __future__ import annotations

from core.ai_core import AICore
from core.agent_registry import AGENT_REGISTRY
from core.quality import ProductionQualityGate
from core.recovery.self_recovery import SelfRecovery


def orchestrate_platform() -> str:
    """Run the initial orchestration pass for the platform."""
    names = [agent.name for agent in AGENT_REGISTRY]
    recovery = SelfRecovery("production", len(AGENT_REGISTRY))
    recovery_payload = recovery.reconcile(expected_environment="production")
    return "Aegis platform initialized with agents: " + ", ".join(names) + " | recovery=" + str(recovery_payload["reconciled"])


def run_agent_workflow(task: str) -> dict:
    """Execute the AI coordination workflow for a single task."""
    ai_core = AICore()
    selected_result = ai_core.dispatch(task)
    workflow_results = ai_core.run_workflow(task)
    quality_gate = ProductionQualityGate.evaluate(task, selected_result["agent_name"], selected_result["response"])

    return {
        "platform_name": "Aegis Agent Platform",
        "agent_count": len(AGENT_REGISTRY),
        "selected_agent": selected_result["agent_name"],
        "results": workflow_results,
        "quality_gate": quality_gate,
    }
