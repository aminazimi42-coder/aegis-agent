"""FastAPI application for the Aegis Agent Platform.

Created by Azimi Innovation Lab.
Owned by AI Architect Amin Azimi.
Developed through the End-to-End System Development model.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from core.ai_core import AICore
from core.monitoring.metrics import PlatformMetrics
from core.quality import ProductionQualityGate
from core.retry_guard import RetryGuard
from core.security import SecurityPolicy, sanitize_payload
from core.task_store import TaskStore
from core.token_optimizer import TokenOptimizer
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.health import health_snapshot, platform_status
from app.api.routes import agent_router, diagnostics_router, task_router, telemetry_router


class TaskDispatchRequest(BaseModel):
    """Request body for dispatching a task to the specialist engine."""

    task: str
    idempotency_key: str | None = None


def create_app() -> FastAPI:
    """Create and configure the production FastAPI application."""
    app = FastAPI(
        title="Aegis Agent Platform",
        version="1.0.0-rc1",
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
    task_store = TaskStore()
    security_policy = SecurityPolicy()
    token_optimizer = TokenOptimizer()
    retry_guard = RetryGuard(max_retries=2)
    app.state.task_store = task_store
    app.state.db_session = task_store
    app.state.security_policy = security_policy
    app.state.token_optimizer = token_optimizer
    app.state.retry_guard = retry_guard

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                raw_body = await request.body()
                if raw_body:
                    try:
                        parsed = json.loads(raw_body)
                        sanitize_payload(parsed)
                    except json.JSONDecodeError:
                        sanitized_text = raw_body.decode("utf-8", errors="ignore")
                        if sanitized_text:
                            security_policy.validate_task(sanitized_text)

                    async def receive() -> dict[str, Any]:
                        return {"type": "http.request", "body": raw_body, "more_body": False}

                    request._receive = receive

                if request.url.path.endswith("/dispatch"):
                    if token_optimizer.throttle_if_needed("dispatch", max_requests_per_minute=30):
                        return JSONResponse(
                            status_code=429,
                            content={
                                "detail": (
                                    "Resource throttling limit reached for this "
                                    "agent dispatch."
                                )
                            },
                        )
                    if token_optimizer._total_tokens >= token_optimizer.daily_budget:
                        return JSONResponse(
                            status_code=429,
                            content={"detail": "Daily token budget exhausted."},
                        )
            except ValueError as exc:
                return JSONResponse(status_code=400, content={"detail": str(exc)})
        return await call_next(request)

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

    @app.post("/tasks/dispatch", tags=["tasks"], status_code=202)
    @app.post("/api/v1/tasks/dispatch", tags=["tasks"], status_code=202)
    async def dispatch_task(request: TaskDispatchRequest) -> dict[str, Any]:
        task_key = request.idempotency_key or request.task
        existing_task = task_store.get_by_idempotency_key(task_key)
        if existing_task is not None:
            return {
                "task_id": existing_task["task_id"],
                "status": existing_task["status"],
                "selected_agent": existing_task.get("selected_agent"),
                "message": "The task already exists in the task store for this idempotency key.",
                "duplicate": True,
            }

        record = task_store.get_or_create(request.task, task_key)

        async def worker() -> None:
            try:
                task_store.update(
                    record["task_id"],
                    status="processing",
                    message="The task is now executing in the async agent workflow.",
                )
                selected_result = retry_guard.execute(
                    record["task_id"],
                    lambda: ai_core.dispatch(record["task"]),
                )
                workflow = retry_guard.execute(
                    f"{record['task_id']}-workflow",
                    lambda: ai_core.run_workflow(record["task"]),
                )
                quality_gate = ProductionQualityGate.evaluate(
                    record["task"],
                    selected_result["agent_name"],
                    selected_result["response"],
                )
                task_store.update(
                    record["task_id"],
                    status="completed",
                    selected_agent=selected_result["agent_name"],
                    message="The async task completed successfully.",
                    result={
                        "workflow": workflow,
                        "agent_count": len(workflow),
                        "platform_status": platform_status(),
                        "quality_gate": quality_gate,
                        "response": selected_result["response"],
                    },
                    telemetry={
                        "request": record["task"],
                        "agent_count": len(workflow),
                        "quality_gate": quality_gate,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "retry_state": retry_guard.snapshot(record["task_id"]),
                    },
                )
            except RuntimeError as exc:
                task_store.update(
                    record["task_id"],
                    status="failed",
                    message=str(exc),
                    telemetry={"retry_state": retry_guard.snapshot(record["task_id"])},
                )

        asyncio.create_task(worker())
        return {
            "task_id": record["task_id"],
            "status": "queued",
            "selected_agent": None,
            "message": "The task was accepted and queued for asynchronous execution.",
            "duplicate": False,
        }

    @app.get("/tasks/{task_id}", tags=["tasks"])
    @app.get("/api/v1/tasks/{task_id}", tags=["tasks"])
    def task_status(task_id: str) -> dict[str, Any]:
        task = task_store.get(task_id)
        if task is None:
            return {
                "task_id": task_id,
                "status": "not_found",
                "telemetry": {"timestamp": datetime.now(timezone.utc).isoformat()},
            }
        payload = dict(task)
        payload["telemetry"] = payload.get(
            "telemetry",
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": payload.get("status", "unknown"),
            },
        )
        return payload

    @app.get("/tasks/{task_id}/status", tags=["tasks"])
    @app.get("/api/v1/tasks/{task_id}/status", tags=["tasks"])
    def task_status_detail(task_id: str) -> dict[str, Any]:
        return task_status(task_id)

    return app


app = create_app()
