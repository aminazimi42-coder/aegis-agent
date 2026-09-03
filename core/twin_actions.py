"""Twin proposed actions with human approval gate (T06).

The twin may *propose* work items derived from the consented profile and
weekly digest, but it must not act until the human approves.  Execution for
this slice is a stub that records ``"executed"`` in SQLite only — no external
side effects.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.persistence import get_connection
from core.twin_interview import get_latest_profile
from core.twin_risk import attach_risk

# ---------------------------------------------------------------------------#
# Constants
# ---------------------------------------------------------------------------#

ACTION_KINDS: tuple[str, ...] = (
    "review_digest",
    "review_repos",
    "prepare_weekly_plan",
)

_VALID_STATUSES: frozenset[str] = frozenset(
    {"proposed", "approved", "rejected", "executed"}
)

_action_lock = threading.Lock()


# ---------------------------------------------------------------------------#
# Schema
# ---------------------------------------------------------------------------#

def _ensure_schema() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS twin_actions (
                action_id   TEXT PRIMARY KEY,
                tenant_id   TEXT    NOT NULL,
                kind        TEXT    NOT NULL,
                title       TEXT    NOT NULL,
                status      TEXT    NOT NULL,
                created_at  TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_twin_actions_tenant
            ON twin_actions (tenant_id)
            """
        )


# ---------------------------------------------------------------------------#
# Internal helpers
# ---------------------------------------------------------------------------#

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """Convert a DB row (or dict) into a plain action dict."""
    if isinstance(row, dict):
        return dict(row)
    return {
        "action_id": row["action_id"],
        "tenant_id": row["tenant_id"],
        "kind": row["kind"],
        "title": row["title"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


def _load_action(action_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT action_id, tenant_id, kind, title, status, created_at "
            "FROM twin_actions WHERE action_id = ?",
            (action_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def _update_status(action_id: str, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE twin_actions SET status = ? WHERE action_id = ?",
            (status, action_id),
        )


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#

def propose_actions(tenant_id: str) -> list[dict[str, Any]]:
    """Deterministically propose work items for ``tenant_id``.

    Requires a consented profile (otherwise ``ValueError`` is raised).
    Returns at least one ``review_digest`` action; additionally
    ``review_repos`` if the profile has non-empty repositories, and
    always ``prepare_weekly_plan``.
    """
    _ensure_schema()
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    actions: list[dict[str, Any]] = []
    now = _now()

    # 1. Always propose review_digest.
    actions.append(
        attach_risk(
            {
                "action_id": f"act-{uuid4().hex[:12]}",
                "tenant_id": tenant_id,
                "kind": "review_digest",
                "title": "Review weekly digest",
                "status": "proposed",
                "created_at": now,
            }
        )
    )

    # 2. Propose review_repos if the profile has repositories.
    repos_raw = profile.get("repositories", "") or ""
    repos = [r.strip() for r in repos_raw.split(",") if r.strip()] if repos_raw else []
    if repos:
        actions.append(
            attach_risk(
                {
                    "action_id": f"act-{uuid4().hex[:12]}",
                    "tenant_id": tenant_id,
                    "kind": "review_repos",
                    "title": f"Review repositories: {', '.join(repos)}",
                    "status": "proposed",
                    "created_at": now,
                }
            )
        )

    # 3. Always propose prepare_weekly_plan.
    actions.append(
        attach_risk(
            {
                "action_id": f"act-{uuid4().hex[:12]}",
                "tenant_id": tenant_id,
                "kind": "prepare_weekly_plan",
                "title": "Prepare weekly plan",
                "status": "proposed",
                "created_at": now,
            }
        )
    )

    # Persist.
    with _action_lock:
        with get_connection() as conn:
            for a in actions:
                conn.execute(
                    "INSERT INTO twin_actions "
                    "(action_id, tenant_id, kind, title, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        a["action_id"],
                        a["tenant_id"],
                        a["kind"],
                        a["title"],
                        a["status"],
                        a["created_at"],
                    ),
                )

    return actions


def approve(action_id: str) -> dict[str, Any]:
    """Set an action's status to ``approved``.

    Raises ``ValueError`` if the action_id is unknown.
    """
    _ensure_schema()
    with _action_lock:
        action = _load_action(action_id)
        if action is None:
            raise ValueError(f"unknown action: {action_id}")
        _update_status(action_id, "approved")
        action["status"] = "approved"
        return action


def reject(action_id: str) -> dict[str, Any]:
    """Set an action's status to ``rejected``.

    Raises ``ValueError`` if the action_id is unknown.
    """
    _ensure_schema()
    with _action_lock:
        action = _load_action(action_id)
        if action is None:
            raise ValueError(f"unknown action: {action_id}")
        _update_status(action_id, "rejected")
        action["status"] = "rejected"
        return action


def execute(action_id: str) -> dict[str, Any]:
    """Execute an approved action (stub: records ``executed`` in SQLite only).

    Raises ``PermissionError("approval required")`` if the action is not
    in the ``approved`` status.  Raises ``ValueError`` if the action_id
    is unknown.
    """
    _ensure_schema()
    with _action_lock:
        action = _load_action(action_id)
        if action is None:
            raise ValueError(f"unknown action: {action_id}")
        if action["status"] != "approved":
            raise PermissionError("approval required")
        _update_status(action_id, "executed")
        action["status"] = "executed"

    # Write evidence ledger entry (best-effort; do not fail if ledger is broken).
    try:
        from core.evidence_ledger import EvidenceLedgerSingleton

        EvidenceLedgerSingleton.append_entry(
            tenant_id=action["tenant_id"],
            actor="twin",
            action="twin_action_executed",
            payload={"action_id": action_id, "kind": action["kind"]},
        )
    except Exception:
        pass

    return action


def list_actions(tenant_id: str) -> list[dict[str, Any]]:
    """Return all actions for ``tenant_id`` ordered by ``created_at``."""
    _ensure_schema()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT action_id, tenant_id, kind, title, status, created_at "
            "FROM twin_actions WHERE tenant_id = ? "
            "ORDER BY created_at ASC",
            (tenant_id,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
