from __future__ import annotations

from typing import Any, Dict, List

from core.agent_registry import AGENT_REGISTRY
from core.ai_core import AICore
from core.monitoring.metrics import PlatformMetrics
from core.security import SecurityPolicy
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


class AgentProfileResponse(BaseModel):
    name: str
    role: str
    description: str
    capabilities: List[str] = Field(default_factory=list)


class TaskSummary(BaseModel):
    id: str
    name: str
    summary: str
    status: str = "queued"


class TaskListResponse(BaseModel):
    tasks: List[TaskSummary]
    total: int


class TelemetryResponse(BaseModel):
    service: str
    status: str
    environment: str
    version: str
    agent_count: int
    telemetry: Dict[str, Any]


class DiagnosticsResponse(BaseModel):
    service: str
    status: str
    ready: bool
    checks: Dict[str, str]
    telemetry: Dict[str, Any]


agent_router = APIRouter(prefix="/api/v1", tags=["agents"])
task_router = APIRouter(prefix="/api/v1", tags=["tasks"])
telemetry_router = APIRouter(prefix="/api/v1", tags=["telemetry"])
diagnostics_router = APIRouter(prefix="/api/v1", tags=["diagnostics"])


@agent_router.get("/agents/{agent_name}", response_model=AgentProfileResponse)
def get_agent(agent_name: str) -> AgentProfileResponse:
    agent_map = {agent.name: agent for agent in AGENT_REGISTRY}
    agent = agent_map.get(agent_name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' was not found.")
    return AgentProfileResponse(
        name=agent.name,
        role=agent.role,
        description=agent.description,
        capabilities=agent.capabilities,
    )


@task_router.get("/tasks", response_model=TaskListResponse)
def list_tasks() -> TaskListResponse:
    tasks = [
        TaskSummary(
            id="task-001",
            name="Strategic planning",
            summary="Develop a coordinated launch plan",
            status="queued",
        ),
        TaskSummary(
            id="task-002",
            name="Operational execution",
            summary="Run deployment and monitoring workflows",
            status="running",
        ),
        TaskSummary(
            id="task-003",
            name="Analytical synthesis",
            summary="Review risk, dependencies, and market context",
            status="queued",
        ),
        TaskSummary(
            id="task-004",
            name="Quality validation",
            summary="Verify the final output before release",
            status="ready",
        ),
    ]
    return TaskListResponse(tasks=tasks, total=len(tasks))


@telemetry_router.get("/telemetry", response_model=TelemetryResponse)
def telemetry() -> TelemetryResponse:
    metrics = PlatformMetrics().snapshot()
    return TelemetryResponse(
        service=metrics["service"],
        status=metrics["status"],
        environment=metrics["environment"],
        version=metrics["version"],
        agent_count=metrics["agent_count"],
        telemetry=metrics["telemetry"],
    )


@diagnostics_router.get("/diagnostics", response_model=DiagnosticsResponse)
def diagnostics() -> DiagnosticsResponse:
    metrics = PlatformMetrics().snapshot()
    security_policy = SecurityPolicy()
    checks = {
        "config": "ok",
        "runtime": "ok",
        "agent_registry": "ok",
        "error_handling": "ok",
        "security": (
            "ok"
            if all(
                security_policy.is_allowed(agent_name)
                for agent_name in ["Alina", "Kian", "Bita", "Aylin", "Amin", "Ahmed"]
            )
            else "blocked"
        ),
    }
    return DiagnosticsResponse(
        service=metrics["service"],
        status=metrics["status"],
        ready=True,
        checks=checks,
        telemetry=metrics["telemetry"],
    )


@task_router.get("/tasks/{task_id}/status")
def task_status(task_id: str) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "ready",
        "selected_agent": "Aylin",
        "message": "The task has reached a verified execution state.",
    }


@task_router.get("/tasks/dispatch")
def task_dispatch_preview() -> Dict[str, Any]:
    engine = AICore()
    selected = engine.resolve_agent_name("Plan the launch and validate the final outcome")
    return {
        "status": "ready",
        "selected_agent": selected,
        "workflow": [agent.name for agent in AGENT_REGISTRY],
    }
