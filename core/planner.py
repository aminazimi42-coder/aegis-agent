from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional

from core.evidence_ledger import EvidenceLedgerSingleton


@dataclass
class Task:
    task_id: str
    tenant_id: str
    title: str
    priority: int = 100
    status: str = "pending"
    assignee: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class AutonomousWorkPlanner:
    """Simple in-memory autonomous planner.

    - add_task: enqueue a task
    - get_next_task: return highest-priority pending task
    - assign_task: mark a task assigned to an actor
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._tasks: Dict[str, Task] = {}

    def add_task(self, tenant_id: str, title: str, priority: int = 100) -> Task:
        tid = str(uuid.uuid4())
        t = Task(task_id=tid, tenant_id=tenant_id, title=title, priority=int(priority))
        with self._lock:
            self._tasks[tid] = t
            EvidenceLedgerSingleton.append_entry(
                tenant_id=tenant_id,
                actor="planner",
                action="add_task",
                payload={"task_id": tid, "title": title, "priority": t.priority},
            )
        return t

    def get_next_task(self, tenant_id: str) -> Optional[Task]:
        with self._lock:
            pending = [
                t
                for t in self._tasks.values()
                if t.tenant_id == tenant_id and t.status == "pending"
            ]
            if not pending:
                return None
            pending.sort(key=lambda x: (x.priority, x.created_at))
            return pending[0]

    def assign_task(self, task_id: str, assignee: str) -> bool:
        with self._lock:
            t = self._tasks.get(task_id)
            if not t or t.status != "pending":
                return False
            t.assignee = assignee
            t.status = "assigned"
            EvidenceLedgerSingleton.append_entry(
                tenant_id=t.tenant_id,
                actor="planner",
                action="assign_task",
                payload={"task_id": task_id, "assignee": assignee},
            )
            return True

    def list_tasks(self, tenant_id: str) -> List[Task]:
        with self._lock:
            return [t for t in self._tasks.values() if t.tenant_id == tenant_id]


PlannerSingleton = AutonomousWorkPlanner()
