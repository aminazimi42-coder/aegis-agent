from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.agent_registry import AGENT_REGISTRY


class BaseAgent(ABC):
    """Base abstraction for all specialist agents in the platform."""

    name: str = "BaseAgent"
    role: str = "Specialist"
    description: str = "Unspecified specialist role."
    capabilities: list[str] = []
    metadata: dict = {}

    def propose(self, tenant_id: str) -> dict[str, Any]:
        """Propose one twin_action row with status ``proposed``.

        Inserts an action whose ``kind`` is prefixed with the agent's
        name (``f"{self.name}:propose"``) via
        :func:`core.twin_actions.insert_specialist_proposal`.

        Specialists must never call ``twin_actions.execute``; the only
        path to ``executed`` is human approval followed by execution.
        """
        from core.twin_actions import insert_specialist_proposal

        title = f"{self.name} proposal for {tenant_id}"
        return insert_specialist_proposal(tenant_id, self.name, title, {})

    def profile(self) -> dict:
        """Return the canonical metadata for the agent."""
        base_profile = {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "capabilities": list(self.capabilities),
        }
        metadata = getattr(self, "metadata", None)
        if metadata:
            base_profile["metadata"] = metadata
        for agent in AGENT_REGISTRY:
            if agent.name == self.name:
                base_profile["name"] = agent.name
                base_profile["role"] = agent.role
                base_profile["description"] = agent.description
                base_profile["capabilities"] = list(agent.capabilities)
                if metadata:
                    base_profile["metadata"] = metadata
                return base_profile
        return base_profile

    def plan(self, task: str) -> str:
        """Generate the specialist plan for a task."""
        return (
            f"{self.name} plan: define the sequence, priorities, "
            f"and risk boundaries for {task}"
        )

    def execute(self, task: str) -> str:
        """Execute the specialist workflow for a task.

        This is a lightweight text-generation stub.  It must **never**
        import or call :func:`core.twin_actions.execute`; the only path
        to an executed twin_action is human approval.
        """
        return (
            f"{self.name} execution: perform the delivery path and "
            f"monitor the operation for {task}"
        )

    def analyze(self, task: str) -> str:
        """Analyze the task with specialist reasoning."""
        return (
            f"{self.name} analysis: evaluate the context, synthesize "
            f"insight, and clarify dependencies for {task}"
        )

    def validate(self, task: str) -> str:
        """Validate the task result before completion."""
        return (
            f"{self.name} validation: verify quality, check completion, "
            f"and confirm the final outcome for {task}"
        )

    def run_engine(self, task: str) -> dict:
        """Return a richer specialist execution payload for SaaS workflows."""
        return {
            "agent": self.name,
            "role": self.profile()["role"],
            "plan": self.plan(task),
            "execution": self.execute(task),
            "analysis": self.analyze(task),
            "validation": self.validate(task),
            "summary": self.handle(task),
        }

    @abstractmethod
    def handle(self, task: str) -> str:
        """Process a task and return a textual response."""
        raise NotImplementedError
