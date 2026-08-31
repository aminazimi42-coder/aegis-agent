from __future__ import annotations

from typing import Any, Callable

from pydantic import ValidationError

from core.agent_registry import AGENT_REGISTRY
from core.ai_core import AICore
from core.schemas import AgentResponse


class TrustAwareModelRouter:
    """Choose the most suitable specialist based on trust-aware routing signals."""

    ROUTE_KEYWORDS = {
        "Alina": [
            "plan",
            "strategy",
            "coordinate",
            "prioritize",
            "roadmap",
            "brief",
        ],
        "Kian": [
            "deploy",
            "execute",
            "run",
            "operate",
            "monitor",
            "runtime",
        ],
        "Bita": [
            "analyze",
            "risk",
            "insight",
            "synthesize",
            "reason",
            "context",
        ],
        "Aylin": [
            "validate",
            "verify",
            "audit",
            "quality",
            "test",
            "check",
        ],
    }

    def __init__(self, max_retries: int = 2) -> None:
        self.max_retries = max(0, int(max_retries))
        self.role_map = {agent.name: agent.role for agent in AGENT_REGISTRY}

    def decide_model(self, task: str, preferred_model: str | None = None) -> str:
        """Select the best model for a task using keyword heuristics."""
        if preferred_model and preferred_model in self.role_map:
            return preferred_model

        normalized = (task or "").lower()
        scores: dict[str, int] = {name: 0 for name in self.role_map}

        for model_name, keywords in self.ROUTE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in normalized:
                    scores[model_name] += 2

        if "privacy" in normalized or "secure" in normalized:
            scores["Bita"] += 2
            scores["Aylin"] += 1

        if "cost" in normalized or "budget" in normalized:
            scores["Alina"] += 2
            scores["Aylin"] += 1

        if "latency" in normalized or "fast" in normalized:
            scores["Kian"] += 2

        chosen = max(scores, key=lambda name: scores[name])
        return chosen if scores[chosen] > 0 else "Alina"

    def evaluate(self, task: str, preferred_model: str | None = None) -> dict[str, Any]:
        """Return trust-aware routing metadata for a candidate task."""
        selected_model = self.decide_model(task, preferred_model)
        normalized = (task or "").lower()

        cost_score = 0.9 if "cost" in normalized or "budget" in normalized else 0.8
        latency_score = 0.95 if "latency" in normalized or "fast" in normalized else 0.85
        privacy_score = 0.95 if "privacy" in normalized or "secure" in normalized else 0.8
        capability_score = 0.9 if selected_model in self.role_map else 0.75

        return {
            "selected_model": selected_model,
            "model_role": self.role_map.get(selected_model, "Specialist"),
            "cost_score": round(cost_score, 3),
            "latency_score": round(latency_score, 3),
            "privacy_score": round(privacy_score, 3),
            "capability_score": round(capability_score, 3),
            "confidence": round(
                (cost_score + latency_score + privacy_score + capability_score) / 4,
                3,
            ),
        }

    def _build_payload(
        self,
        task: str,
        model_name: str | None = None,
        factory: Callable | None = None,
    ) -> dict[str, Any]:
        selected_model = self.decide_model(task, model_name)

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

    def route(
        self,
        task: str,
        factory: Callable | None = None,
        model_name: str | None = None,
    ) -> AgentResponse:
        """Route a task with bounded retries and strict schema validation."""
        selected_model = self.decide_model(task, model_name)

        for attempt in range(self.max_retries + 1):
            try:
                payload = self._build_payload(task, selected_model, factory)
                validated = AgentResponse.model_validate(payload)
                validated.status = "completed"
                return validated
            except ValidationError as exc:
                if attempt >= self.max_retries:
                    raise ValueError(
                        f"Schema validation failed after {self.max_retries} retry "
                        f"attempts: {exc}"
                    ) from exc
                continue

        raise ValueError("Model routing failed without producing a valid schema payload.")
