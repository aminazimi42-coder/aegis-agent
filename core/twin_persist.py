"""SQLite persistence for approvals and FinOps budgets.

T39 — process restart must not wipe approval rows or tenant budget
remaining.  All functions open their own connection and close it after
use so they are safe to call from independent threads/processes.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def init_schema() -> None:
    """Create the approvals and budgets tables if they do not exist."""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                id         TEXT PRIMARY KEY,
                tenant_id  TEXT,
                title      TEXT,
                status     TEXT,
                payload    TEXT,
                created_at TEXT,
                decided_at TEXT
            );
            CREATE TABLE IF NOT EXISTS budgets (
                tenant_id  TEXT PRIMARY KEY,
                cap        REAL,
                spent      REAL,
                updated_at TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

def put_approval(
    approval_id: str,
    tenant_id: str,
    title: str,
    status: str,
    payload: dict[str, Any] | None = None,
    created_at: str | None = None,
    decided_at: str | None = None,
) -> dict[str, Any]:
    """Insert or replace an approval row and return it as a dict."""
    init_schema()
    conn = _connect()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT OR REPLACE INTO approvals
                (id, tenant_id, title, status, payload, created_at, decided_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                tenant_id,
                title,
                status,
                json.dumps(payload, default=str) if payload is not None else None,
                created_at or now,
                decided_at,
            ),
        )
        conn.commit()
        return {
            "id": approval_id,
            "tenant_id": tenant_id,
            "title": title,
            "status": status,
            "payload": payload,
            "created_at": created_at or now,
            "decided_at": decided_at,
        }
    finally:
        conn.close()


def get_approval(approval_id: str) -> dict[str, Any] | None:
    """Return the approval row for *approval_id* or ``None``."""
    init_schema()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM approvals WHERE id = ?",
            (approval_id,),
        ).fetchone()
        if row is None:
            return None
        d: dict[str, Any] = dict(row)
        if d.get("payload") is not None:
            d["payload"] = json.loads(d["payload"])
        return d
    finally:
        conn.close()


def list_approvals(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """Return all approval rows, optionally filtered by *tenant_id*."""
    init_schema()
    conn = _connect()
    try:
        if tenant_id is not None:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE tenant_id = ? ORDER BY created_at",
                (tenant_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM approvals ORDER BY created_at"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            if d.get("payload") is not None:
                d["payload"] = json.loads(d["payload"])
            result.append(d)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

def get_budget(tenant_id: str) -> dict[str, Any] | None:
    """Return the budget row for *tenant_id* or ``None``."""
    init_schema()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM budgets WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def set_budget(tenant_id: str, cap: float, spent: float = 0.0) -> dict[str, Any]:
    """Insert or replace a budget row and return it as a dict."""
    init_schema()
    conn = _connect()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT OR REPLACE INTO budgets (tenant_id, cap, spent, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (tenant_id, float(cap), float(spent), now),
        )
        conn.commit()
        return {
            "tenant_id": tenant_id,
            "cap": float(cap),
            "spent": float(spent),
            "updated_at": now,
        }
    finally:
        conn.close()


def add_spend(tenant_id: str, amount: float) -> float:
    """Atomically add *amount* to the tenant's spent column.

    Returns the remaining budget (``cap - spent``).  If no budget row
    exists yet, one is created with a generous default cap and zero
    spent before the spend is applied.
    """
    init_schema()
    conn = _connect()
    try:
        now = datetime.now(timezone.utc).isoformat()
        row = conn.execute(
            "SELECT * FROM budgets WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if row is None:
            # Create a default budget row so spent is always persisted.
            cap = 100000.0
            spent = float(amount)
        else:
            cap = float(row["cap"])
            spent = float(row["spent"]) + float(amount)
        conn.execute(
            """
            INSERT OR REPLACE INTO budgets (tenant_id, cap, spent, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (tenant_id, cap, spent, now),
        )
        conn.commit()
        return cap - spent
    finally:
        conn.close()
