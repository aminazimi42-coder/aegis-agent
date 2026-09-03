from __future__ import annotations

from typing import Any, Dict, List

from agents.ahmad.agent import AhmadAgent
from agents.alina.agent import AlinaAgent
from agents.amin.agent import AminAgent
from agents.aylin.agent import AylinAgent
from agents.bita.agent import BitaAgent
from agents.kian.agent import KianAgent

from core.agent_registry import AGENT_REGISTRY
from core.llm_provider import LLMProvider, get_provider
from core.model_router import TrustAwareModelRouter
from core.token_optimizer import TokenOptimizer


class AICore:
    """Core coordination layer for routing tasks to the correct agent."""

    def __init__(self) -> None:
        self.registry = {agent.name: agent for agent in AGENT_REGISTRY}
        self.token_optimizer = TokenOptimizer()
        self.llm_provider: LLMProvider = get_provider()
        self.model_router = TrustAwareModelRouter()
        self.agent_map = {
            "Alina": AlinaAgent(),
            "Kian": KianAgent(),
            "Bita": BitaAgent(),
            "Aylin": AylinAgent(),
            "Ahmad": AhmadAgent(),
            "Amin": AminAgent(),
        }

    def resolve_agent_name(self, task: str) -> str:
        """Select the most appropriate agent for a given task string."""
        lower_task = task.lower()

        if any(
            keyword in lower_task
            for keyword in [
                "plan", "strategy", "coordinate", "prioritize", "route",
            ]
        ):
            return "Alina"
        if any(
            keyword in lower_task
            for keyword in [
                "execute", "deploy", "run", "operate", "monitor", "optimize",
            ]
        ):
            return "Kian"
        if any(
            keyword in lower_task
            for keyword in [
                "analyze", "reason", "synthesize", "summarize", "risk", "insight",
            ]
        ):
            return "Bita"
        if any(
            keyword in lower_task
            for keyword in [
                "validate", "verify", "check", "quality", "audit", "test",
            ]
        ):
            return "Aylin"
        if any(
            keyword in lower_task
            for keyword in [
                "security", "kms", "oversight", "incident", "sandbox",
                "authority", "key rotation", "secure",
            ]
        ):
            return "Ahmad"
        if any(
            keyword in lower_task
            for keyword in [
                "finance", "invoice", "settlement", "budget", "token economy",
                "pay", "charge", "settle",
            ]
        ):
            return "Amin"
        return "Alina"

    def catalog(self) -> List[Dict[str, Any]]:
        """Return the canonical metadata catalog for the platform agents."""
        return [
            {
                "name": agent.name,
                "role": agent.role,
                "description": agent.description,
                "capabilities": agent.capabilities,
            }
            for agent in AGENT_REGISTRY
        ]

    def dispatch(self, task: str) -> Dict[str, Any]:
        """Dispatch a task to a specialist and return the result payload."""
        cached_response = self.token_optimizer.get_cached_response(task)
        if cached_response is not None:
            agent_name = self.resolve_agent_name(task)
            model = self.model_router.decide_llm_model(task)
            return {
                "agent_name": agent_name,
                "response": cached_response,
                "task": task,
                "cached": True,
                "model": model,
                "tokens": 0,
            }

        agent_name = self.resolve_agent_name(task)
        agent = self.agent_map[agent_name]
        model = self.model_router.decide_llm_model(task)
        prompt = agent.handle(task)
        result = self.llm_provider.complete(prompt, model=model, max_tokens=512)
        response = result["text"]
        tokens = result["total_tokens"]
        self.token_optimizer.record_usage(task, agent_name, response, model=model)
        self.token_optimizer.cache_response(task, agent_name, response)

        return {
            "agent_name": agent_name,
            "response": response,
            "task": task,
            "cached": False,
            "model": model,
            "tokens": tokens,
        }

    def run_workflow(self, task: str) -> List[Dict[str, Any]]:
        """Collect the specialized output of all six agents for a task."""
        ordered_names = ["Alina", "Kian", "Bita", "Aylin", "Ahmad", "Amin"]
        results: List[Dict[str, Any]] = []

        for name in ordered_names:
            agent = self.agent_map[name]
            response = agent.handle(task)
            self.token_optimizer.record_usage(task, name, response)
            self.token_optimizer.cache_response(task, name, response)
            results.append(
                {
                    "agent_name": name,
                    "role": agent.profile()["role"],
                    "response": response,
                    "task": task,
                }
            )

        return results
