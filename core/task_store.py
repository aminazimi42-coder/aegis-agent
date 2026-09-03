"""Thread-safe task tracking for queued agent workflows.

Task records are persisted to SQLite so that a new ``TaskStore`` instance
pointing at the same ``AEGIS_DATA_DIR`` sees prior tasks.
"""

from __future__ import annotations

import json
from threading import Lock
from typing import Any
from uuid import uuid4

from core.persistence import get_connection


class TaskStore:
    """Store task records and idempotency keys used by the async worker loop."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._idempotency_index: dict[str, str] = {}
        self._lock = Lock()
        self._ensure_schema()
        self._load_from_db()

    def _ensure_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_store (
                    task_id          TEXT PRIMARY KEY,
                    task             TEXT NOT NULL,
                    status           TEXT NOT NULL DEFAULT 'queued',
                    selected_agent   TEXT,
                    message          TEXT,
                    idempotency_key  TEXT,
                    result           TEXT,
                    extra            TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_idempotency (
                    idempotency_key TEXT PRIMARY KEY,
                    task_id         TEXT NOT NULL
                )
                """
            )

    def _load_from_db(self) -> None:
        with get_connection() as conn:
            cur = conn.execute(
                "SELECT task_id, task, status, selected_agent, message, "
                "idempotency_key, result FROM task_store"
            )
            for row in cur:
                record: dict[str, Any] = {
                    "task_id": row["task_id"],
                    "task": row["task"],
                    "status": row["status"],
                    "selected_agent": row["selected_agent"],
                    "message": row["message"],
                    "idempotency_key": row["idempotency_key"],
                    "result": json.loads(row["result"]) if row["result"] else None,
                }
                self._tasks[row["task_id"]] = record
                idem_key = row["idempotency_key"]
                if idem_key:
                    self._idempotency_index[idem_key] = row["task_id"]

    def _persist_task(self, record: dict[str, Any]) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO task_store "
                "(task_id, task, status, selected_agent, message, idempotency_key, result) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record["task_id"],
                    record.get("task", ""),
                    record.get("status", "queued"),
                    record.get("selected_agent"),
                    record.get("message"),
                    record.get("idempotency_key"),
                    json.dumps(record.get("result")) if record.get("result") else None,
                ),
            )
            idem_key = record.get("idempotency_key")
            if idem_key:
                conn.execute(
                    "INSERT OR REPLACE INTO task_idempotency (idempotency_key, task_id) "
                    "VALUES (?, ?)",
                    (idem_key, record["task_id"]),
                )

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
            self._persist_task(record)
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
            self._persist_task(record)
            return record

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._tasks.values())
