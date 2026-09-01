from __future__ import annotations

from core.agent_registry import AGENT_REGISTRY
from core.ai_core import AICore
from core.finops_autopilot import FinOpsAutopilot
from core.quality import ProductionQualityGate
from core.recovery.self_recovery import SelfRecovery
from core.retry_guard import RetryGuard
from core.shadow_swarm import ShadowSwarmRunner
from core.tenant_memory import TenantMemoryVault


def orchestrate_platform() -> str:
    """Run the initial orchestration pass for the platform."""
    names = [agent.name for agent in AGENT_REGISTRY]
    recovery = SelfRecovery("production", len(AGENT_REGISTRY))
    recovery_payload = recovery.reconcile(expected_environment="production")
    return (
        "Aegis platform initialized with agents: "
        + ", ".join(names)
        + " | recovery="
        + str(recovery_payload["reconciled"])
    )


def run_agent_workflow(task: str, tenant_id: str = "default") -> dict:
    """Execute the AI coordination workflow for a single task."""
    ai_core = AICore()
    retry_guard = RetryGuard(max_retries=2)
    finops_autopilot = FinOpsAutopilot()
    tenant_memory = TenantMemoryVault(default_ttl_seconds=3600)
    shadow_runner = ShadowSwarmRunner()
    finops_autopilot.enforce_budget(tenant_id, task)

    def execute_workflow() -> dict:
        tenant_memory.store(
            tenant_id=tenant_id,
            key="workflow-context",
            value={"task": task, "status": "active"},
            namespace="agent-workflow",
            ttl_seconds=300,
        )
        context = tenant_memory.read(
            tenant_id,
            "workflow-context",
            namespace="agent-workflow",
        )

        selected_result = ai_core.dispatch(task)
        workflow_results = ai_core.run_workflow(task)
        # Run the shadow swarm in-process to capture divergence and consensus
        shadow_result = shadow_runner.execute_and_compare(task)
        finops_usage = finops_autopilot.record_usage(
            tenant_id,
            task,
            selected_result["agent_name"],
            prompt_tokens=max(1, len(task.split())),
        )
        quality_gate = ProductionQualityGate.evaluate(
            task,
            selected_result["agent_name"],
            selected_result["response"],
        )
        tenant_memory.store(
            tenant_id=tenant_id,
            key="workflow-context",
            value={"task": task, "status": "completed", "context": context},
            namespace="agent-workflow",
            ttl_seconds=300,
        )
        return {
            "platform_name": "Aegis Agent Platform",
            "agent_count": len(AGENT_REGISTRY),
            "selected_agent": selected_result["agent_name"],
            "results": workflow_results,
            "quality_gate": quality_gate,
            "retry_state": retry_guard.snapshot(task),
            "finops": finops_usage,
            "shadow": {
                "divergence_score": shadow_result.divergence_score,
                "consensus": shadow_result.consensus,
                "details": shadow_result.details,
            },
            "tenant_memory": tenant_memory.read(
                tenant_id,
                "workflow-context",
                namespace="agent-workflow",
            ),
        }

    return retry_guard.execute(task, execute_workflow)
