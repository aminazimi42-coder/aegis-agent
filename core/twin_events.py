"""Twin event ingestion for the Aegis Agent platform.

Events are structured work signals (git commits, editor edits, calendar
meetings, manual notes) that feed the deterministic twin-evolution loop.

Every event is persisted to the ``twin_events`` SQLite table via
``core.persistence`` and is associated with a tenant that must already
have a *consented* (committed) twin profile.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.persistence import get_connection
from core.twin_interview import get_latest_profile

# ---------------------------------------------------------------------------#
# Event dataclass
# ---------------------------------------------------------------------------#

_VALID_SOURCES = {"git", "editor", "calendar", "manual", "email"}
_VALID_KINDS = {"commit", "edit", "meeting", "note", "message"}


@dataclass
class Event:
    """A single structured work event."""

    event_id: str
    tenant_id: str
    source: str
    kind: str
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------#
# Schema
# ---------------------------------------------------------------------------#

_ensure_lock = threading.Lock()


def _ensure_schema() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS twin_events (
                event_id    TEXT PRIMARY KEY,
                tenant_id   TEXT NOT NULL,
                source      TEXT NOT NULL,
                kind        TEXT NOT NULL,
                payload     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_twin_events_tenant
            ON twin_events (tenant_id, created_at)
            """
        )


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#

def ingest_event(
    tenant_id: str,
    source: str,
    kind: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ingest a single work event for ``tenant_id``.

    Raises ``ValueError`` if no committed twin profile exists for the
    tenant ("no consented profile") or if ``source``/``kind`` are invalid.

    Returns the persisted event as a dict.
    """
    if source not in _VALID_SOURCES:
        raise ValueError(f"invalid source: {source!r}")
    if kind not in _VALID_KINDS:
        raise ValueError(f"invalid kind: {kind!r}")

    with _ensure_lock:
        _ensure_schema()
        profile = get_latest_profile(tenant_id)
        if profile is None:
            raise ValueError("no consented profile")
        event_id = f"evt-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        event = Event(
            event_id=event_id,
            tenant_id=tenant_id,
            source=source,
            kind=kind,
            payload=payload or {},
            created_at=now,
        )
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO twin_events "
                "(event_id, tenant_id, source, kind, payload, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.tenant_id,
                    event.source,
                    event.kind,
                    json.dumps(event.payload),
                    event.created_at,
                ),
            )
        return event.to_dict()


def list_events(tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent events for ``tenant_id`` (newest first)."""
    _ensure_schema()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM twin_events WHERE tenant_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (tenant_id, limit),
        ).fetchall()
    return [
        {
            "event_id": r["event_id"],
            "tenant_id": r["tenant_id"],
            "source": r["source"],
            "kind": r["kind"],
            "payload": json.loads(r["payload"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]
