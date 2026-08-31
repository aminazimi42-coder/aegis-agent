"""Thread-safe in-memory task tracking for queued agent workflows."""

from __future__ import annotations

from threading import Lock
from typing import Any
from uuid import uuid4


class TaskStore:
    """Store task records and idempotency keys used by the async worker loop."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._idempotency_index: dict[str, str] = {}
        self._lock = Lock()

    def get_or_create(self, task: str, idempotency_key: str | None = None) -> dict[str, Any]:
        key = idempotency_key or task
        with self._lock:
            existing_task_id = self._idempotency_index.get(key)
            if existing_task_id is not None:
                return self._tasks[existing_task_id]

            task_id = f"task-{uuid4().hex[:10]}"
            record = {
                "task_id": task_id,
                "task": task,
                "status": "queued",
                "selected_agent": None,
                "message": "Queued for execution.",
                "idempotency_key": key,
                "result": None,
            }
            self._tasks[task_id] = record
            self._idempotency_index[key] = task_id
            return record

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._tasks.get(task_id)

    def get_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        with self._lock:
            task_id = self._idempotency_index.get(idempotency_key)
            if task_id is None:
                return None
            return self._tasks.get(task_id)

    def update(self, task_id: str, **values: Any) -> dict[str, Any]:
        with self._lock:
            record = self._tasks.setdefault(task_id, {"task_id": task_id})
            record.update(values)
            return record

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._tasks.values())
