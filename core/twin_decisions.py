"""Searchable yes/no decision log for the cognitive twin.

``record(tenant_id, title, decision, reason)`` persists a single yes/no
decision (with a reason) to the ``twin_decisions`` SQLite table, then
rewrites ``work_products/{tenant_id}/decision_log.md`` with the full list.

``list_decisions(tenant_id, *, query="")`` returns the decisions for a
tenant, optionally filtered by a case-insensitive substring match on
**title** or **reason**.

Deterministic, no LLM, no network — pure SQLite via ``core.persistence``.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.persistence import get_connection
from core.twin_interview import get_latest_profile

# ---------------------------------------------------------------------------#
# Schema
# ---------------------------------------------------------------------------#

_ensure_lock = threading.Lock()


def _ensure_schema() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS twin_decisions (
                id          TEXT PRIMARY KEY,
                tenant_id   TEXT NOT NULL,
                title       TEXT NOT NULL,
                decision    TEXT NOT NULL,
                reason      TEXT NOT NULL,
                created_at  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_twin_decisions_tenant
            ON twin_decisions (tenant_id, created_at)
            """
        )


# ---------------------------------------------------------------------------#
# Work-product file
# ---------------------------------------------------------------------------#


def _decision_log_path(tenant_id: str) -> Path:
    """Return the path to ``decision_log.md`` for *tenant_id*."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id / "decision_log.md"


def _write_decision_log(tenant_id: str, decisions: list[dict[str, Any]]) -> Path:
    """Write the full decision list as markdown and return the file path."""
    lines: list[str] = [
        f"# Decision Log — {tenant_id}",
        "",
    ]
    if not decisions:
        lines.append("_No decisions recorded yet._")
        lines.append("")
    else:
        for i, d in enumerate(decisions, start=1):
            lines.append(
                f"{i}. **{d['decision'].upper()}** — {d['title']}"
            )
            if d.get("reason"):
                lines.append(f"   - _Reason:_ {d['reason']}")
            lines.append("")

    out_path = _decision_log_path(tenant_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#


def record(
    tenant_id: str,
    title: str,
    decision: str,
    reason: str,
) -> dict[str, Any]:
    """Record a single yes/no decision for *tenant_id*.

    ``decision`` must be ``"yes"`` or ``"no"`` (case-sensitive) — otherwise
    ``ValueError("invalid decision")`` is raised.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).

    Persists the row to the ``twin_decisions`` table, then rewrites
    ``work_products/{tenant_id}/decision_log.md`` with the full list and
    returns the new decision as a dict.
    """
    if decision not in ("yes", "no"):
        raise ValueError("invalid decision")

    with _ensure_lock:
        _ensure_schema()
        profile = get_latest_profile(tenant_id)
        if profile is None:
            raise ValueError("no consented profile")

        decision_id = f"dec-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO twin_decisions "
                "(id, tenant_id, title, decision, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (decision_id, tenant_id, title, decision, reason, now),
            )

        result = {
            "id": decision_id,
            "tenant_id": tenant_id,
            "title": title,
            "decision": decision,
            "reason": reason,
            "created_at": now,
        }

        # Rewrite the full decision log on each record.
        all_decisions = list_decisions(tenant_id)
        _write_decision_log(tenant_id, all_decisions)

        return result


def list_decisions(
    tenant_id: str,
    *,
    query: str = "",
) -> list[dict[str, Any]]:
    """Return decisions for *tenant_id*, optionally filtered by *query*.

    When *query* is non-empty, only rows whose **title** or **reason**
    contains *query* (case-insensitive) are returned.  Newest first.
    """
    _ensure_schema()
    q = query.strip().lower()
    with get_connection() as conn:
        if q:
            rows = conn.execute(
                "SELECT * FROM twin_decisions WHERE tenant_id = ? "
                "AND (LOWER(title) LIKE ? OR LOWER(reason) LIKE ?) "
                "ORDER BY created_at DESC",
                (tenant_id, f"%{q}%", f"%{q}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM twin_decisions WHERE tenant_id = ? "
                "ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()

    return [
        {
            "id": r["id"],
            "tenant_id": r["tenant_id"],
            "title": r["title"],
            "decision": r["decision"],
            "reason": r["reason"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
