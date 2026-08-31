from __future__ import annotations

from typing import Any, Callable

from pydantic import ValidationError

from core.agent_registry import AGENT_REGISTRY
from core.ai_core import AICore
from core.schemas import AgentResponse, TaskValidationResult


class SmartModelRouter:
    """Validates and retries structured agent responses before accepting them."""

    def __init__(self, max_retries: int = 2) -> None:
        self.max_retries = max(0, max_retries)
        self.role_map = {agent.name: agent.role for agent in AGENT_REGISTRY}

    def choose_model(self, task: str, preferred_model: str | None = None) -> str:
        """Choose the most appropriate agent route for a task."""
        if preferred_model is not None:
            return preferred_model

        normalized = task.lower()
        if any(keyword in normalized for keyword in ["plan", "strategy", "coordinate", "prioritize"]):
            return "Alina"
        if any(keyword in normalized for keyword in ["execute", "deploy", "run", "operate", "monitor"]):
            return "Kiyan"
        if any(keyword in normalized for keyword in ["analyze", "reason", "synthesize", "risk", "insight"]):
            return "Bita"
        if any(keyword in normalized for keyword in ["validate", "verify", "check", "quality", "audit"]):
            return "Aylin"
        return "Alina"

    def validate_payload(self, task: str, payload: dict[str, Any]) -> TaskValidationResult:
        """Validate a candidate payload using the strict agent response schema."""
        try:
            response = AgentResponse.model_validate(payload)
            return TaskValidationResult(
                task=task,
                valid=True,
                agent_name=response.agent_name,
                retries_used=0,
            )
        except ValidationError as exc:
            return TaskValidationResult(
                task=task,
                valid=False,
                retries_used=0,
                error=str(exc),
            )

    def _build_payload(self, task: str, model_name: str | None = None, factory: Callable | None = None) -> dict[str, Any]:
        selected_model = self.choose_model(task, model_name)

        if factory is not None:
            payload = factory(task, selected_model)
            if not isinstance(payload, dict):
                raise TypeError("Router factory must return a dictionary payload.")
            return payload

        ai_core = AICore()
        result = ai_core.dispatch(task)
        return {
            "agent_name": result["agent_name"],
            "role": self.role_map.get(result["agent_name"], "Specialist"),
            "response": result["response"],
            "task": task,
            "status": "completed",
            "model": selected_model,
        }

    def route(self, task: str, factory: Callable | None = None, model_name: str | None = None) -> AgentResponse:
        """Attempt a task route with bounded retry handling for schema mismatch."""
        selected_model = self.choose_model(task, model_name)

        for attempt in range(self.max_retries + 1):
            try:
                payload = self._build_payload(task, selected_model, factory)
                validated = AgentResponse.model_validate(payload)
                validated.status = "completed"
                return validated
            except ValidationError as exc:
                if attempt >= self.max_retries:
                    raise ValueError(
                        f"Schema validation failed after {self.max_retries} retry attempts: {exc}"
                    ) from exc
                continue

        raise ValueError("Model routing failed without producing a valid schema payload.")
