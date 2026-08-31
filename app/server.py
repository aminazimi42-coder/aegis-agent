"""FastAPI application for the Aegis Agent Platform.

Created by Azimi Innovation Lab.
Owned by AI Architect Amin Azimi.
Developed through the End-to-End System Development model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.ai_core import AICore
from core.monitoring.metrics import PlatformMetrics
from core.quality import ProductionQualityGate
from fastapi import FastAPI
from pydantic import BaseModel

from app.api.health import health_snapshot, platform_status
from app.api.routes import agent_router, diagnostics_router, task_router, telemetry_router


class TaskDispatchRequest(BaseModel):
    """Request body for dispatching a task to the specialist engine."""

    task: str


def create_app() -> FastAPI:
    """Create and configure the production FastAPI application."""
    app = FastAPI(
        title="Aegis Agent Platform",
        version="0.6.0-a",
        description="Production web API for the multi-agent SaaS platform.",
        openapi_tags=[
            {
                "name": "health",
                "description": "Runtime liveness and service health endpoints.",
            },
            {
                "name": "metrics",
                "description": "Operational telemetry and service metrics.",
            },
            {
                "name": "agents",
                "description": "Multi-agent registry and specialist catalog endpoints.",
            },
            {
                "name": "tasks",
                "description": "Task execution, status, and workflow endpoints.",
            },
            {
                "name": "telemetry",
                "description": "Telemetry, runtime health, and SaaS monitoring signals.",
            },
            {
                "name": "diagnostics",
                "description": "Runtime diagnostics and readiness checks.",
            },
        ],
    )
    metrics = PlatformMetrics()
    ai_core = AICore()
    app.include_router(agent_router)
    app.include_router(task_router)
    app.include_router(telemetry_router)
    app.include_router(diagnostics_router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, Any]:
        payload = health_snapshot()
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        return payload

    @app.get("/metrics", tags=["metrics"])
    def metrics_endpoint() -> dict[str, Any]:
        payload = metrics.snapshot()
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        return payload

    @app.get("/api/v1/agents", tags=["agents"])
    def list_agents() -> dict[str, Any]:
        agents = ai_core.catalog()
        return {"agents": agents, "agent_count": len(agents)}

    @app.post("/api/v1/tasks/dispatch", tags=["tasks"])
    def dispatch_task(request: TaskDispatchRequest) -> dict[str, Any]:
        selected_result = ai_core.dispatch(request.task)
        workflow = ai_core.run_workflow(request.task)
        quality_gate = ProductionQualityGate.evaluate(
            request.task,
            selected_result["agent_name"],
            selected_result["response"],
        )

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
