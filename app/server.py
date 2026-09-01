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
from core.finops_autopilot import FinOpsAutopilot
from core.model_router import TrustAwareModelRouter
from core.monitoring.metrics import PlatformMetrics
from core.observability import CausalSwarmObservability
from core.quality import ProductionQualityGate
from core.retry_guard import RetryGuard
from core.security import SecurityPolicy, sanitize_payload
from core.task_store import TaskStore
from core.tenant_memory import TenantMemoryVault
from core.token_optimizer import TokenOptimizer
from core.tool_tokens import ToolTokenManager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.health import health_snapshot, platform_status
from app.api.routes import agent_router, diagnostics_router, task_router, telemetry_router


class TaskDispatchRequest(BaseModel):
    """Request body for dispatching a task to the specialist engine."""

    task: str
    idempotency_key: str | None = None
    tenant_id: str | None = None


class ToolIssueRequest(BaseModel):
    """Issue a scoped capability token for a tool call."""

    tenant_id: str
    task_id: str
    tool_name: str
    capabilities: list[str] | None = None
    ttl_seconds: int | None = None


class ToolExecutionRequest(BaseModel):
    """Execute a tool only after the caller presents a valid capability token."""

    tool_name: str
    tenant_id: str
    task_id: str
    required_capabilities: list[str] | None = None
    payload: dict[str, Any] | None = None
    token: str | None = None


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
    finops_autopilot = FinOpsAutopilot()
    model_router = TrustAwareModelRouter()
    tool_token_manager = ToolTokenManager()
    tenant_memory = TenantMemoryVault(default_ttl_seconds=3600)
    observability = CausalSwarmObservability(default_ttl_seconds=3600)
    retry_guard = RetryGuard(max_retries=2)
    app.state.task_store = task_store
    app.state.db_session = task_store
    app.state.security_policy = security_policy
    app.state.token_optimizer = token_optimizer
    app.state.finops_autopilot = finops_autopilot
    app.state.model_router = model_router
    app.state.tool_token_manager = tool_token_manager
    app.state.tenant_memory = tenant_memory
    app.state.observability = observability
    app.state.retry_guard = retry_guard

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        trace = observability.trace_request(
            tenant_id=request.headers.get("x-tenant-id") or "default",
            kind="request",
            metadata={"path": request.url.path, "method": request.method},
        )
        request.state.trace = trace
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                raw_body = await request.body()
                parsed: Any = None
                tenant_id = request.headers.get("x-tenant-id") or "default"
                if raw_body:
                    try:
                        parsed = json.loads(raw_body)
                        sanitize_payload(parsed)
                        if isinstance(parsed, dict):
                            tenant_id = str(
                                parsed.get("tenant_id")
                                or parsed.get("tenant")
                                or tenant_id
                            )
                            task_text = parsed.get("task")
                            if isinstance(task_text, str):
                                finops_autopilot.enforce_budget(tenant_id, task_text)
                                request.state.route_decision = model_router.evaluate(
                                    task_text,
                                    parsed.get("model_name"),
                                )
                                parsed["model_name"] = request.state.route_decision[
                                    "selected_model"
                                ]

                            memory_key = parsed.get("memory_key")
                            memory_namespace = str(
                                parsed.get("memory_namespace") or "default"
                            )
                            if memory_key is not None:
                                if parsed.get("memory_value") is not None:
                                    tenant_memory.store(
                                        tenant_id=tenant_id,
                                        key=str(memory_key),
                                        value=parsed["memory_value"],
                                        namespace=memory_namespace,
                                        ttl_seconds=parsed.get("memory_ttl_seconds"),
                                    )
                                else:
                                    tenant_memory.authorize_access(
                                        tenant_id,
                                        str(memory_key),
                                        namespace=memory_namespace,
                                    )
                    except json.JSONDecodeError:
                        sanitized_text = raw_body.decode("utf-8", errors="ignore")
                        if sanitized_text:
                            security_policy.validate_task(sanitized_text)
                            finops_autopilot.enforce_budget(tenant_id, sanitized_text)

                    async def receive() -> dict[str, Any]:
                        return {"type": "http.request", "body": raw_body, "more_body": False}

                    request._receive = receive

                if request.url.path.endswith("/dispatch"):
                    observability.record_event(
                        trace,
                        "request_body_received",
                        {"path": request.url.path, "tenant_id": tenant_id},
                    )
                    if token_optimizer.throttle_if_needed(
                        "dispatch",
                        max_requests_per_minute=30,
                    ):
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
            except (ValueError, RuntimeError) as exc:
                response_code = 429 if isinstance(exc, RuntimeError) else 400
                return JSONResponse(
                    status_code=response_code,
                    content={"detail": str(exc)},
                )
        response = await call_next(request)
        observability.record_metric("requests_total", 1)
        observability.record_event(
            trace,
            "request_completed",
            {"status": response.status_code, "path": request.url.path},
        )
        return response

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

    @app.post("/api/v1/tools/issue", tags=["tools"], status_code=200)
    @app.post("/tools/issue", tags=["tools"], status_code=200)
    def issue_tool_token(request: ToolIssueRequest) -> dict[str, Any]:
        token = tool_token_manager.issue_token(
            tenant_id=request.tenant_id,
            task_id=request.task_id,
            tool_name=request.tool_name,
            capabilities=request.capabilities or ["read"],
            ttl_seconds=request.ttl_seconds,
        )
        return {
            "token": token,
            "tool_name": request.tool_name,
            "tenant_id": request.tenant_id,
            "task_id": request.task_id,
            "capabilities": request.capabilities or ["read"],
            "expires_at": datetime.now(timezone.utc).isoformat(),
        }

    @app.post("/api/v1/tools/execute", tags=["tools"], status_code=200)
    @app.post("/tools/execute", tags=["tools"], status_code=200)
    async def execute_tool(request: Request) -> dict[str, Any]:
        body = await request.json()
        tool_request = ToolExecutionRequest(**body)
        auth_header = request.headers.get("authorization")
        token = tool_request.token
        if auth_header and not token:
            token = auth_header
        try:
            validated = tool_token_manager.authorize_headers(
                authorization=auth_header,
                tool_name=tool_request.tool_name,
                required_capabilities=tool_request.required_capabilities or ["read"],
                tenant_id=tool_request.tenant_id,
                task_id=tool_request.task_id,
            )
        except (PermissionError, ValueError) as exc:
            return JSONResponse(
                status_code=403,
                content={"detail": str(exc), "tool_name": tool_request.tool_name},
            )

        return {
            "status": "authorized",
            "tool_name": validated.tool_name,
            "tenant_id": validated.tenant_id,
            "task_id": validated.task_id,
            "capabilities": list(validated.capabilities),
            "payload": tool_request.payload,
        }

    @app.post("/tasks/dispatch", tags=["tasks"], status_code=202)
    @app.post("/api/v1/tasks/dispatch", tags=["tasks"], status_code=202)
    async def dispatch_task(request: TaskDispatchRequest) -> dict[str, Any]:
        tenant_id = request.tenant_id or "default"
        try:
            finops_autopilot.enforce_budget(tenant_id, request.task)
        except RuntimeError as exc:
            return JSONResponse(
                status_code=429,
                content={"detail": str(exc), "tenant_id": tenant_id},
            )

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
                usage = finops_autopilot.record_usage(
                    tenant_id,
                    record["task"],
                    selected_result["agent_name"],
                    prompt_tokens=len(record["task"].split()),
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
                        "finops": usage,
                    },
                    telemetry={
                        "request": record["task"],
                        "agent_count": len(workflow),
                        "quality_gate": quality_gate,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "retry_state": retry_guard.snapshot(record["task_id"]),
                        "finops": usage,
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
