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
from core.evidence_ledger import EvidenceLedgerSingleton
from core.finops_autopilot import FinOpsAutopilot
from core.human_authority import HumanAuthority
from core.model_router import TrustAwareModelRouter
from core.monitoring.metrics import PlatformMetrics
from core.observability import CausalSwarmObservability
from core.quality import ProductionQualityGate
from core.retry_guard import RetryGuard
from core.scorecard import ScorecardSingleton
from core.security import SecurityPolicy, sanitize_payload
from core.task_store import TaskStore
from core.tenant_memory import TenantMemoryVault
from core.token_optimizer import TokenOptimizer
from core.tool_tokens import ToolTokenManager
from core.twin_actions import (
    approve as twin_action_approve,
)
from core.twin_actions import (
    execute as twin_action_execute,
)
from core.twin_actions import (
    list_actions as twin_action_list,
)
from core.twin_actions import (
    propose_actions as twin_action_propose,
)
from core.twin_actions import (
    reject as twin_action_reject,
)
from core.twin_behavior import (
    get_behavior as twin_get_behavior,
)
from core.twin_behavior import (
    rebuild as twin_rebuild_behavior,
)
from core.twin_calendar import ingest_ics as twin_ingest_ics
from core.twin_decisions import list_decisions as twin_list_decisions
from core.twin_decisions import record as twin_record_decision
from core.twin_delegate_pack import render_pack as twin_render_pack
from core.twin_email_triage import triage as twin_email_triage
from core.twin_events import ingest_event as twin_ingest_event
from core.twin_evolution import evolve as twin_evolve
from core.twin_evolution import weekly_digest as twin_weekly_digest
from core.twin_expenses import ingest_receipts as twin_ingest_receipts
from core.twin_focus_block import create_block as twin_create_focus_block
from core.twin_followups import render_followups as twin_render_followups
from core.twin_git_observer import observe_repo as twin_observe_repo
from core.twin_github_observer import observe_github as twin_observe_github
from core.twin_interview import (
    answer as twin_answer,
)
from core.twin_interview import (
    commit as twin_commit,
)
from core.twin_interview import (
    get_latest_profile as twin_get_latest,
)
from core.twin_interview import (
    start_session as twin_start,
)
from core.twin_meeting_brief import render_meetings as twin_render_meetings
from core.twin_morning_brief import render_brief as twin_render_brief
from core.twin_pr_review import review_diff as twin_review_diff
from core.twin_style_lock import lock_style as twin_lock_style
from core.twin_team_inbox import triage as twin_team_inbox_triage
from core.twin_travel_pack import render_pack as twin_render_travel_pack
from core.twin_work_products import render as twin_render_work_products
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


class TwinSessionStartRequest(BaseModel):
    """Body for starting a cognitive-twin interview session."""

    tenant_id: str


class TwinAnswerRequest(BaseModel):
    """Body for submitting a single interview answer."""

    question_id: str
    text: str


class TwinCommitRequest(BaseModel):
    """Body for committing a completed interview as a profile."""

    consent: bool


class TwinEventRequest(BaseModel):
    """Body for ingesting a work event into the twin evolution loop."""

    tenant_id: str
    source: str
    kind: str
    payload: dict[str, Any] = {}


class TwinObserveGitRequest(BaseModel):
    """Body for observing a local git repo and feeding commits to the twin."""

    tenant_id: str
    repo_path: str
    max_commits: int = 20


class TwinActionProposeRequest(BaseModel):
    """Body for proposing twin actions from the profile + digest."""

    tenant_id: str


class TwinObserveGithubRequest(BaseModel):
    """Body for observing a GitHub repo via PAT."""

    tenant_id: str
    repo: str
    max_commits: int = 20


class TwinBehaviorRebuildRequest(BaseModel):
    """Body for rebuilding the versioned behavioral snapshot."""

    tenant_id: str


class TwinWorkProductsRenderRequest(BaseModel):
    """Body for rendering local work-product files."""

    tenant_id: str


class TwinCalendarIcsRequest(BaseModel):
    """Body for ingesting a local .ics calendar file."""

    tenant_id: str
    ics_path: str


class TwinMorningBriefRequest(BaseModel):
    """Body for rendering a one-page morning brief."""

    tenant_id: str


class TwinEmailTriageRequest(BaseModel):
    """Body for triaging a folder of .eml files."""

    tenant_id: str
    mail_dir: str


class TwinMeetingBriefsRequest(BaseModel):
    """Body for rendering per-meeting briefs."""

    tenant_id: str


class TwinFollowupsRequest(BaseModel):
    """Body for rendering the follow-up list."""

    tenant_id: str


class TwinDelegatePackRequest(BaseModel):
    """Body for rendering the delegate pack."""

    tenant_id: str


class TwinDecisionRecordRequest(BaseModel):
    """Body for recording a yes/no decision."""

    tenant_id: str
    title: str
    decision: str
    reason: str


class TwinStyleLockRequest(BaseModel):
    """Body for locking a writing-style profile from local text samples."""

    tenant_id: str
    samples_dir: str


class TwinPrReviewRequest(BaseModel):
    """Body for turning a local diff into PR review notes."""

    tenant_id: str
    diff_path: str


class TwinExpensesIngestRequest(BaseModel):
    """Body for ingesting a folder of receipt .txt files into expense notes."""

    tenant_id: str
    receipts_dir: str


class TwinFocusBlockRequest(BaseModel):
    """Body for creating a local focus-block hold (markdown + .ics)."""

    tenant_id: str
    start: str
    duration_min: int = 90
    title: str = "Focus"


class TwinTravelPackRequest(BaseModel):
    """Body for rendering a one-page travel pack from calendar + docs."""

    tenant_id: str
    docs_dir: str = ""


class TwinTeamInboxRequest(BaseModel):
    """Body for triaging a local team-chat export into a markdown page."""

    tenant_id: str
    export_path: str


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
    human_authority = HumanAuthority()
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
    app.state.human_authority = human_authority
    # lightweight in-memory approval store for Phase16
    app.state.approvals: dict[str, dict] = {}

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

    # --- Approval endpoints (Phase16 governance) ---

    @app.post("/approvals/request", tags=["diagnostics"])
    async def request_approval(request: Request) -> dict[str, Any]:
        body = await request.json()
        action = body.get("action", "")
        tenant_id = body.get("tenant_id", "default")
        # evaluate risk
        tenant_sensitive = body.get("tenant_sensitive", False)
        profile = human_authority.evaluate_risk(action, {"tenant_sensitive": tenant_sensitive})
        approval_id = f"appr-{len(app.state.approvals)+1}"
        status = "pending"
        if profile.level.name == "AUTO":
            status = "approved"
        app.state.approvals[approval_id] = {
            "action": action,
            "tenant_id": tenant_id,
            "profile": profile.__dict__,
            "status": status,
        }
        # record evidence and scorecard
        try:
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor=body.get("requester", "system"),
                action="approval_requested",
                payload={"approval_id": approval_id, "status": status, "action": action},
            )
            ScorecardSingleton.record_approval(tenant_id, required=(profile.level.name != "AUTO"))
        except Exception:
            pass
        return {"approval_id": approval_id, "status": status, "profile": profile.__dict__}

    @app.post("/approvals/{approval_id}/decide", tags=["diagnostics"]) 
    async def decide_approval(approval_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        decision = body.get("decision")
        approver = body.get("approver", "unknown")
        if approval_id not in app.state.approvals:
            return JSONResponse(status_code=404, content={"detail": "approval_id not found"})
        if decision not in {"approve", "deny"}:
            return JSONResponse(
                status_code=400,
                content={"detail": "decision must be 'approve' or 'deny'"},
            )
        record = app.state.approvals[approval_id]
        record["status"] = "approved" if decision == "approve" else "denied"
        # ledger evidence
        try:
            EvidenceLedgerSingleton.append_entry(
                tenant_id=record.get("tenant_id", "default"),
                actor=approver,
                action="approval_decision",
                payload={"approval_id": approval_id, "decision": decision},
            )
        except Exception:
            pass
        return {"approval_id": approval_id, "decision": decision}

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

    # --- Cognitive-twin interview (T03) ---

    @app.post("/api/v1/twin/session/start", tags=["twin"], status_code=200)
    def twin_session_start(request: TwinSessionStartRequest) -> dict[str, Any]:
        return twin_start(request.tenant_id)

    @app.post(
        "/api/v1/twin/session/{session_id}/answer", tags=["twin"], status_code=200
    )
    def twin_session_answer(
        session_id: str, request: TwinAnswerRequest
    ) -> dict[str, Any]:
        return twin_answer(session_id, request.question_id, request.text)

    @app.post(
        "/api/v1/twin/session/{session_id}/commit", tags=["twin"], status_code=200
    )
    def twin_session_commit(
        session_id: str, request: TwinCommitRequest
    ) -> dict[str, Any]:
        return twin_commit(session_id, request.consent)

    @app.get("/api/v1/twin/profile/{tenant_id}", tags=["twin"])
    def twin_profile_get(tenant_id: str) -> Any:
        profile = twin_get_latest(tenant_id)
        if profile is None:
            return JSONResponse(
                status_code=404,
                content={"detail": "no committed profile for this tenant"},
            )
        return profile

    # --- Twin evolution (T04) ---

    @app.post("/api/v1/twin/events", tags=["twin"], status_code=200)
    def twin_event_ingest(request: TwinEventRequest) -> Any:
        try:
            event = twin_ingest_event(
                tenant_id=request.tenant_id,
                source=request.source,
                kind=request.kind,
                payload=request.payload,
            )
            evolved = twin_evolve(request.tenant_id, event)
            return {"event": event, "profile": evolved}
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    @app.get("/api/v1/twin/digest/{tenant_id}", tags=["twin"])
    def twin_digest_get(tenant_id: str) -> Any:
        try:
            return twin_weekly_digest(tenant_id)
        except ValueError as exc:
            return JSONResponse(
                status_code=404,
                content={"detail": str(exc)},
            )

    # --- Twin local git observer (T05) ---

    @app.post("/api/v1/twin/observe/git", tags=["twin"], status_code=200)
    def twin_observe_git(request: TwinObserveGitRequest) -> Any:
        try:
            return twin_observe_repo(
                tenant_id=request.tenant_id,
                repo_path=request.repo_path,
                max_commits=request.max_commits,
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin GitHub PAT observer (T10) ---

    @app.post("/api/v1/twin/observe/github", tags=["twin"], status_code=200)
    def twin_observe_github_endpoint(request: TwinObserveGithubRequest) -> Any:
        try:
            return twin_observe_github(
                tenant_id=request.tenant_id,
                repo=request.repo,
                max_commits=request.max_commits,
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin behavioral memory (T11) ---

    @app.post(
        "/api/v1/twin/behavior/rebuild", tags=["twin"], status_code=200
    )
    def twin_behavior_rebuild(
        request: TwinBehaviorRebuildRequest,
    ) -> Any:
        try:
            return twin_rebuild_behavior(request.tenant_id)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    @app.get("/api/v1/twin/behavior/{tenant_id}", tags=["twin"])
    def twin_behavior_get(tenant_id: str) -> Any:
        result = twin_get_behavior(tenant_id)
        if result is None:
            return JSONResponse(
                status_code=404,
                content={"detail": "no behavior snapshot for this tenant"},
            )
        return result

    # --- Twin local work products (T12) ---

    @app.post(
        "/api/v1/twin/work-products/render", tags=["twin"], status_code=200
    )
    def twin_work_products_render(
        request: TwinWorkProductsRenderRequest,
    ) -> Any:
        try:
            return twin_render_work_products(request.tenant_id)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin local ICS calendar ingest (T14) ---

    @app.post("/api/v1/twin/calendar/ics", tags=["twin"], status_code=200)
    def twin_calendar_ics(request: TwinCalendarIcsRequest) -> Any:
        try:
            return twin_ingest_ics(request.tenant_id, request.ics_path)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin morning brief (T18) ---

    @app.post("/api/v1/twin/brief/morning", tags=["twin"], status_code=200)
    def twin_morning_brief(request: TwinMorningBriefRequest) -> Any:
        try:
            return twin_render_brief(request.tenant_id)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin email triage (T19) ---

    @app.post("/api/v1/twin/email/triage", tags=["twin"], status_code=200)
    def twin_email_triage_endpoint(request: TwinEmailTriageRequest) -> Any:
        try:
            return twin_email_triage(request.tenant_id, request.mail_dir)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin meeting briefs (T20) ---

    @app.post("/api/v1/twin/brief/meetings", tags=["twin"], status_code=200)
    def twin_meeting_briefs(request: TwinMeetingBriefsRequest) -> Any:
        try:
            return twin_render_meetings(request.tenant_id)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin follow-ups (T21) ---

    @app.post("/api/v1/twin/followups/render", tags=["twin"], status_code=200)
    def twin_followups_render(request: TwinFollowupsRequest) -> Any:
        try:
            return twin_render_followups(request.tenant_id)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin delegate pack (T22) ---

    @app.post("/api/v1/twin/delegate/render", tags=["twin"], status_code=200)
    def twin_delegate_pack_render(request: TwinDelegatePackRequest) -> Any:
        try:
            return twin_render_pack(request.tenant_id)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin decisions (T23) ---

    @app.post("/api/v1/twin/decisions", tags=["twin"], status_code=200)
    def twin_decision_record(request: TwinDecisionRecordRequest) -> Any:
        try:
            return twin_record_decision(
                request.tenant_id,
                request.title,
                request.decision,
                request.reason,
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    @app.get("/api/v1/twin/decisions/{tenant_id}", tags=["twin"])
    def twin_decision_list(tenant_id: str, q: str = "") -> Any:
        decisions = twin_list_decisions(tenant_id, query=q)
        return {"decisions": decisions, "count": len(decisions)}

    # --- Twin style lock (T24) ---

    @app.post("/api/v1/twin/style/lock", tags=["twin"], status_code=200)
    def twin_style_lock(request: TwinStyleLockRequest) -> Any:
        try:
            return twin_lock_style(request.tenant_id, request.samples_dir)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin PR review (T25) ---

    @app.post("/api/v1/twin/pr/review", tags=["twin"], status_code=200)
    def twin_pr_review(request: TwinPrReviewRequest) -> Any:
        try:
            return twin_review_diff(request.tenant_id, request.diff_path)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin expenses (T26) ---

    @app.post("/api/v1/twin/expenses/ingest", tags=["twin"], status_code=200)
    def twin_expenses_ingest(request: TwinExpensesIngestRequest) -> Any:
        try:
            return twin_ingest_receipts(request.tenant_id, request.receipts_dir)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin focus block (T27) ---

    @app.post("/api/v1/twin/focus/block", tags=["twin"], status_code=200)
    def twin_focus_block(request: TwinFocusBlockRequest) -> Any:
        try:
            return twin_create_focus_block(
                request.tenant_id,
                request.start,
                duration_min=request.duration_min,
                title=request.title,
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin travel pack (T28) ---

    @app.post("/api/v1/twin/travel/render", tags=["twin"], status_code=200)
    def twin_travel_pack_render(request: TwinTravelPackRequest) -> Any:
        try:
            return twin_render_travel_pack(request.tenant_id, request.docs_dir)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin team inbox (T29) ---

    @app.post("/api/v1/twin/team/inbox", tags=["twin"], status_code=200)
    def twin_team_inbox(request: TwinTeamInboxRequest) -> Any:
        try:
            return twin_team_inbox_triage(request.tenant_id, request.export_path)
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    # --- Twin proposed actions with human approval gate (T06) ---

    @app.post("/api/v1/twin/actions/propose", tags=["twin"], status_code=200)
    def twin_actions_propose(
        request: TwinActionProposeRequest,
    ) -> Any:
        try:
            actions = twin_action_propose(request.tenant_id)
            return {"actions": actions, "count": len(actions)}
        except ValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

    @app.post(
        "/api/v1/twin/actions/{action_id}/approve", tags=["twin"], status_code=200
    )
    def twin_actions_approve(action_id: str) -> Any:
        try:
            return twin_action_approve(action_id)
        except ValueError as exc:
            return JSONResponse(
                status_code=404,
                content={"detail": str(exc)},
            )

    @app.post(
        "/api/v1/twin/actions/{action_id}/reject", tags=["twin"], status_code=200
    )
    def twin_actions_reject(action_id: str) -> Any:
        try:
            return twin_action_reject(action_id)
        except ValueError as exc:
            return JSONResponse(
                status_code=404,
                content={"detail": str(exc)},
            )

    @app.post(
        "/api/v1/twin/actions/{action_id}/execute", tags=["twin"], status_code=200
    )
    def twin_actions_execute(action_id: str) -> Any:
        try:
            return twin_action_execute(action_id)
        except PermissionError as exc:
            return JSONResponse(
                status_code=403,
                content={"detail": str(exc)},
            )
        except ValueError as exc:
            return JSONResponse(
                status_code=404,
                content={"detail": str(exc)},
            )

    @app.get("/api/v1/twin/actions/{tenant_id}", tags=["twin"])
    def twin_actions_list(tenant_id: str) -> Any:
        actions = twin_action_list(tenant_id)
        return {"actions": actions, "count": len(actions)}

    # --- Production integrity (T07) --- #

    @app.get("/api/v1/platform/status", tags=["twin"])
    def platform_status_endpoint() -> Any:
        from core.platform_status import platform_status as _status

        return _status()

    return app


app = create_app()
