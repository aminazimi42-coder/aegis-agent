from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.agent_registry import AGENT_REGISTRY

# T159 — profile fields that may appear in a propose body when present
# in the stored profile.  Only non-empty values are included; absent
# fields are omitted rather than invented.
_PROFILE_FIELDS: tuple[str, ...] = (
    "role",
    "decision_style",
    "tools",
    "risk_posture",
    "work_ethics",
    "repositories",
)


def propose_profile_fields(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Return only the profile fields that are present and non-empty.

    T159 — when building a propose body, do not add name, role, goals,
    timezone, or other profile fields that are absent from the stored
    local profile.  If a field is missing or empty, omit it.  Do not
    guess.  Echo path included (the ``repositories`` field is the
    display name).
    """
    if profile is None:
        return {}
    fields: dict[str, Any] = {}
    for key in _PROFILE_FIELDS:
        val = profile.get(key)
        if val is not None and str(val).strip():
            fields[key] = val
    return fields



class BaseAgent(ABC):
    """Base abstraction for all specialist agents in the platform."""

    name: str = "BaseAgent"
    role: str = "Specialist"
    description: str = "Unspecified specialist role."
    capabilities: list[str] = []
    metadata: dict = {}

    def _propose_body(self, text: str) -> str:
        """Return the role-shaped proposal body for *text*.

        Default behaviour (T112 — echo): the body is the operator text
        unchanged.  Specialists override this to produce a distinct,
        deterministic, role-shaped body that still includes the text.
        """
        return text

    def propose(
        self, tenant_id: str, text: str = "", batch_id: str | None = None
    ) -> dict[str, Any]:
        """Propose one twin_action row with status ``proposed``.

        Inserts an action whose ``kind`` is prefixed with the agent's
        name (``f"{self.name}:propose"``) via
        :func:`core.twin_actions.insert_specialist_proposal`.

        When *text* is non-empty (T111 — operator page propose), it is
        included in the action title and payload so the operator's task
        text is visible in the queue.  The payload also carries a
        ``body`` field (T112) produced by :meth:`_propose_body` so each
        specialist's row is distinguishable.  When *text* is empty the
        pre-T111 behaviour is preserved (empty payload).

        T120 — *batch_id* tags all rows from one propose call so the
        two-column home can split the newest batch (Latest) from older
        batches (Archive).  When *batch_id* is ``None`` the row is
        inserted with a ``NULL`` batch_id (treated as archive).

        T130 — the payload also carries ``recent_notes``: the last N
        local style/risk feedback notes for this tenant (approve/reject
        decisions) so the specialist brief is shaped by prior outcomes.

        Specialists must never call ``twin_actions.execute``; the only
        path to ``executed`` is human approval followed by execution.
        """
        from core.twin_actions import insert_specialist_proposal, list_recent_notes

        title = f"{self.name} proposal for {tenant_id}"
        payload: dict[str, Any] = {}
        if text:
            title = f"{self.name} proposal: {text}"
            payload = {"text": text, "body": self._propose_body(text)}
        # T130 — attach the last N local feedback notes to the brief.
        payload["recent_notes"] = list_recent_notes(tenant_id)
        # T159 — attach only the profile fields that are present in the
        # stored local profile; do not invent name, role, goals,
        # timezone, or any field the stored profile does not contain.
        from core.twin_interview import get_latest_profile

        payload["profile_fields"] = propose_profile_fields(
            get_latest_profile(tenant_id)
        )
        return insert_specialist_proposal(
            tenant_id, self.name, title, payload, batch_id=batch_id
        )

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
