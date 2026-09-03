"""Durable commitment scheduler (T41).

A Monday-10:00 commitment must survive process restart.  ``schedule()``
persists a job row in SQLite; ``tick()`` only marks due rows — it does **not**
execute side effects, send email, or open sockets.

Public API::

    from core.twin_scheduler import schedule, tick, list_jobs
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.twin_persist import init_schema


def _db_path() -> Path:
    """Return the path to the SQLite database file."""
    return Path(os.getenv("AEGIS_DATA_DIR", "data")) / "aegis.sqlite"


def _connect() -> sqlite3.Connection:
    """Open a new connection to the SQLite database (creates the file)."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema() -> None:
    """Create the jobs table if it does not exist."""
    init_schema()


def _has_consented_profile(tenant_id: str) -> bool:
    """Return True when *tenant_id* has at least one committed profile."""
    try:
        from core.twin_interview import get_latest_profile

        return get_latest_profile(tenant_id) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------

def schedule(
    tenant_id: str,
    title: str,
    due_at: str,
    timezone_: str = "UTC",
) -> dict[str, Any]:
    """Persist a new scheduled job and return it as a dict.

    Raises ``ValueError("no consented profile")`` when *tenant_id* has no
    committed profile.
    """
    if not _has_consented_profile(tenant_id):
        raise ValueError("no consented profile")
    _ensure_schema()
    job_id = f"job-{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO jobs (id, tenant_id, title, due_at, timezone, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, tenant_id, title, due_at, timezone_, "scheduled", now),
        )
        conn.commit()
        return {
            "id": job_id,
            "tenant_id": tenant_id,
            "title": title,
            "due_at": due_at,
            "timezone": timezone_,
            "status": "scheduled",
            "created_at": now,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# list_jobs
# ---------------------------------------------------------------------------

def list_jobs(
    tenant_id: str,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Return all jobs for *tenant_id*, optionally filtered by *status*."""
    _ensure_schema()
    conn = _connect()
    try:
        if status is not None:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE tenant_id = ? AND status = ? ORDER BY created_at",
                (tenant_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE tenant_id = ? ORDER BY created_at",
                (tenant_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# tick
# ---------------------------------------------------------------------------

def tick(now: str | None = None) -> list[dict[str, Any]]:
    """Mark scheduled jobs whose ``due_at`` <= *now* as ``"due"``.

    Returns the list of jobs that were flipped.  Does **not** execute any
    side effects, send email, or open sockets.
    """
    _ensure_schema()
    if now is None:
        now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = 'scheduled' AND due_at <= ?",
            (now,),
        ).fetchall()
        due: list[dict[str, Any]] = []
        for row in rows:
            conn.execute(
                "UPDATE jobs SET status = 'due' WHERE id = ?",
                (row["id"],),
            )
            due.append(dict(row))
        conn.commit()
        # Update the status in the returned dicts to reflect the flip.
        for d in due:
            d["status"] = "due"
        return due
    finally:
        conn.close()
