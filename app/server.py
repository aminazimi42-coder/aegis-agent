"""FastAPI application for the Aegis Agent Platform.

Created by Azimi Innovation Lab.
Owned by AI Architect Amin Azimi.
Developed through the End-to-End System Development model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app.api.health import health_snapshot, platform_status
from core.ai_core import AICore
from core.monitoring.metrics import PlatformMetrics
from core.quality import ProductionQualityGate


class TaskDispatchRequest(BaseModel):
    """Request body for dispatching a task to the specialist engine."""

    task: str


def create_app() -> FastAPI:
    """Create and configure the production FastAPI application."""
    app = FastAPI(
        title="Aegis Agent Platform",
        version="0.5.0",
        description="Production web API for the multi-agent SaaS platform.",
    )
    metrics = PlatformMetrics()
    ai_core = AICore()

    @app.get("/health")
    def health() -> dict[str, Any]:
        payload = health_snapshot()
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        return payload

    @app.get("/metrics")
    def metrics_endpoint() -> dict[str, Any]:
        payload = metrics.snapshot()
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        return payload

    @app.get("/api/v1/agents")
    def list_agents() -> dict[str, Any]:
        agents = ai_core.catalog()
        return {"agents": agents, "agent_count": len(agents)}

    @app.post("/api/v1/tasks/dispatch")
    def dispatch_task(request: TaskDispatchRequest) -> dict[str, Any]:
        selected_result = ai_core.dispatch(request.task)
        workflow = ai_core.run_workflow(request.task)
        quality_gate = ProductionQualityGate.evaluate(request.task, selected_result["agent_name"], selected_result["response"])

        return {
            "selected_agent": selected_result["agent_name"],
            "task": request.task,
            "status": "completed",
            "results": workflow,
            "agent_count": len(workflow),
            "platform_status": platform_status(),
            "quality_gate": quality_gate,
        }

    return app


app = create_app()
