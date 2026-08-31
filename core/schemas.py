from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class AgentResponse(BaseModel):
    """Strict response payload for any routed agent output."""

    model_config = ConfigDict(extra="forbid")

    agent_name: Literal["Alina", "Kiyan", "Bita", "Aylin"]
    role: str
    response: str
    task: str
    status: Literal["completed", "failed", "retrying"] = "completed"
    model: str = "deterministic-router"


class TaskValidationResult(BaseModel):
    """Validation outcome for a routed task payload."""

    task: str
    valid: bool
    agent_name: str | None = None
    retries_used: int = 0
    error: str | None = None
