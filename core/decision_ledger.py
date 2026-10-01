"""Tenant-bound local decision ledger (T211).

Records one row per Approve or Reject on the local operator under
``AEGIS_DATA_DIR``.  The ledger is a local SQLite table in the same
``aegis.sqlite`` database used by the rest of the twin.  No network, no
cloud, no ``$HOME`` writes outside ``AEGIS_DATA_DIR``.

Each row:

* ``tenant_id`` — the tenant that owns the decision.
* ``action_id`` — the twin action id being decided.
* ``specialist`` — the specialist name (may be empty).
* ``decision`` — ``"approve"`` or ``"reject"``.
* ``reason_code`` — a T117 taxonomy label or empty string.
* ``digest_prefix`` — first 12 chars of the action payload SHA-256, or empty.
* ``created_at`` — UTC ISO timestamp.

Public API:

* ``append(tenant_id, row)`` — write one row, scoped to *tenant_id* only.
* ``list(tenant_id)`` — return rows for *tenant_id* only, newest last, cap 50.
* ``forget(tenant_id)`` — delete all rows for *tenant_id*; neighbor rows stay.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from core.persistence import get_connection

_lock = threading.Lock()

_MAX_ROWS = 50


def _ensure_schema() -> None:
    """Create the ``decision_ledger`` table if it does not exist."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_ledger (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id     TEXT    NOT NULL,
                action_id     TEXT    NOT NULL,
                specialist    TEXT    NOT NULL DEFAULT '',
                decision      TEXT    NOT NULL,
                reason_code   TEXT    NOT NULL DEFAULT '',
                digest_prefix TEXT    NOT NULL DEFAULT '',
                created_at    TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_decision_ledger_tenant
            ON decision_ledger (tenant_id, id)
            """
        )


def append(tenant_id: str, row: dict[str, Any]) -> dict[str, Any]:
    """Append one decision row for *tenant_id*.

    ``row`` must contain ``action_id`` and ``decision`` (``"approve"`` or
    ``"reject"``).  ``specialist``, ``reason_code``, and ``digest_prefix``
    are optional and default to empty strings.  ``created_at`` is set
    automatically to the current UTC timestamp.
    """
    action_id = row.get("action_id", "")
    decision = row.get("decision", "")
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be 'approve' or 'reject'")
    if not action_id:
        raise ValueError("action_id required")
    specialist = row.get("specialist", "") or ""
    reason_code = row.get("reason_code", "") or ""
    digest_prefix = row.get("digest_prefix", "") or ""
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        _ensure_schema()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO decision_ledger "
                "(tenant_id, action_id, specialist, decision, "
                " reason_code, digest_prefix, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (tenant_id, action_id, specialist, decision,
                 reason_code, digest_prefix, now),
            )
    return {
        "tenant_id": tenant_id,
        "action_id": action_id,
        "specialist": specialist,
        "decision": decision,
        "reason_code": reason_code,
        "digest_prefix": digest_prefix,
        "created_at": now,
    }


def list(tenant_id: str) -> list[dict[str, Any]]:  # noqa: A001
    """Return decision rows for *tenant_id* only, newest last, cap 50.

    A neighbor tenant always returns an empty list — never cross-tenant
    rows.
    """
    _ensure_schema()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tenant_id, action_id, specialist, decision, "
            "       reason_code, digest_prefix, created_at "
            "FROM decision_ledger WHERE tenant_id = ? "
            "ORDER BY id ASC LIMIT ?",
            (tenant_id, _MAX_ROWS),
        ).fetchall()
    return [
        {
            "tenant_id": r["tenant_id"],
            "action_id": r["action_id"],
            "specialist": r["specialist"],
            "decision": r["decision"],
            "reason_code": r["reason_code"],
            "digest_prefix": r["digest_prefix"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def recent(
    tenant_id: str,
    n: int = 8,
    ttl_hours: int = 168,
) -> list[dict[str, Any]]:
    """Return at most *n* recent rows for *tenant_id* within the TTL.

    Rows whose ``created_at`` is older than *ttl_hours* from now are
    skipped — they stay on disk until :func:`forget` but are not
    returned.  Newest last.  A neighbor tenant always returns ``[]``.
    """
    _ensure_schema()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl_hours)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tenant_id, action_id, specialist, decision, "
            "       reason_code, digest_prefix, created_at "
            "FROM decision_ledger "
            "WHERE tenant_id = ? AND created_at >= ? "
            "ORDER BY id DESC LIMIT ?",
            (tenant_id, cutoff, n),
        ).fetchall()
    rows = rows[::-1]
    return [
        {
            "tenant_id": r["tenant_id"],
            "action_id": r["action_id"],
            "specialist": r["specialist"],
            "decision": r["decision"],
            "reason_code": r["reason_code"],
            "digest_prefix": r["digest_prefix"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def hours_saved(tenant_id: str) -> dict[str, Any]:
    """Return hours saved from the local decision ledger for *tenant_id*.

    The number is a count of approved local decisions in the ledger
    window (TTL), times a fixed local weight of fifteen minutes, shown
    as a number of hours.  It is labeled ``local ledger count`` — it is
    not a behavioral twin and not a multi-month claim.  A neighbor
    tenant always returns zero; a missing ledger returns zero, not an
    error.  The number must not unlock execute and must not change
    entitlement.
    """
    _MINUTES_PER_DECISION = 15
    try:
        rows = recent(tenant_id)
    except Exception:
        rows = []
    approved = [r for r in rows if r.get("decision") == "approve"]
    count = len(approved)
    hours = round(count * _MINUTES_PER_DECISION / 60, 2)
    return {
        "tenant_id": tenant_id,
        "hours_saved": hours,
        "label": "local ledger count",
        "approved_count": count,
    }


def forget(tenant_id: str) -> int:
    """Delete all decision rows for *tenant_id*; neighbor rows stay.

    Returns the number of rows deleted.
    """
    _ensure_schema()
    with _lock:
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM decision_ledger WHERE tenant_id = ?",
                (tenant_id,),
            )
            return cur.rowcount
