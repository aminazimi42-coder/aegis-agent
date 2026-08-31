from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExecutionState(str, Enum):
    """Execution lifecycle states for each agent task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentSpec:
    """Static descriptor for a single agent."""

    name: str
    role: str
    description: str
    capabilities: list[str] = field(default_factory=list)


@dataclass
class TaskMessage:
    """Unit of work passed between orchestrator and agents."""

    task_id: str
    agent_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    state: ExecutionState = ExecutionState.PENDING
