"""Versioned behavioral-memory snapshots derived from twin events.

The behavior snapshot is a deterministic, reproducible summary of the work
events accumulated for a tenant.  It is *not* a live LLM — it is pure
computation over the ``twin_events`` table plus the consented twin profile.

Snapshots are persisted to a dedicated ``twin_behavior`` SQLite table and
versioned: a rebuild that produces an identical snapshot keeps the previous
version, while a changed snapshot bumps the version by one.
"""

from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from core.persistence import get_connection
from core.twin_events import list_events
from core.twin_interview import get_latest_profile

_behavior_lock = threading.Lock()

_MAX_SUBJECTS = 5


# ---------------------------------------------------------------------------#
# Schema
# ---------------------------------------------------------------------------#

def _ensure_schema() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS twin_behavior (
                tenant_id   TEXT PRIMARY KEY,
                version     INTEGER NOT NULL,
                snapshot     TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
            """
        )


# ---------------------------------------------------------------------------#
# Snapshot derivation
# ---------------------------------------------------------------------------#

def _derive_snapshot(tenant_id: str) -> dict[str, Any]:
    """Build a deterministic snapshot dict from twin_events for *tenant_id*."""
    events = list_events(tenant_id, limit=1000)

    sources: Counter[str] = Counter()
    repos: list[str] = []
    repo_seen: set[str] = set()
    subjects: Counter[str] = Counter()

    for ev in events:
        src = ev.get("source", "")
        if src:
            sources[src] += 1

        payload = ev.get("payload") or {}
        if ev.get("source") == "git" and ev.get("kind") == "commit":
            repo = payload.get("repo") or payload.get("repo_name")
            if repo and repo not in repo_seen:
                repo_seen.add(repo)
                repos.append(repo)
            subject = payload.get("subject")
            if subject:
                subjects[subject] += 1

    top_subjects = [
        subject for subject, _ in subjects.most_common(_MAX_SUBJECTS)
    ]

    return {
        "tenant_id": tenant_id,
        "event_count": len(events),
        "sources": dict(sources),
        "repos": repos,
        "top_subjects": top_subjects,
    }


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#

def rebuild(tenant_id: str) -> dict[str, Any]:
    """Rebuild and persist the behavioral snapshot for *tenant_id*.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).  Derives the snapshot purely from ``twin_events``
    for the tenant, persists it to the ``twin_behavior`` table, and returns
    the stored snapshot dict (including ``version`` and ``updated_at``).

    If the derived snapshot is identical to the previously stored one the
    version is preserved; otherwise the version increments by one.
    """
    with _behavior_lock:
        _ensure_schema()
        if get_latest_profile(tenant_id) is None:
            raise ValueError("no consented profile")

        snapshot = _derive_snapshot(tenant_id)
        now = datetime.now(timezone.utc).isoformat()

        with get_connection() as conn:
            row = conn.execute(
                "SELECT version, snapshot FROM twin_behavior WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()

            snapshot_json = json.dumps(snapshot, sort_keys=True)

            if row is not None:
                prev_version = int(row["version"])
                prev_snapshot_json = row["snapshot"]
                if prev_snapshot_json == snapshot_json:
                    version = prev_version
                else:
                    version = prev_version + 1
                conn.execute(
                    "UPDATE twin_behavior "
                    "SET version = ?, snapshot = ?, updated_at = ? "
                    "WHERE tenant_id = ?",
                    (version, snapshot_json, now, tenant_id),
                )
            else:
                version = 1
                conn.execute(
                    "INSERT INTO twin_behavior "
                    "(tenant_id, version, snapshot, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (tenant_id, version, snapshot_json, now),
                )

        return {
            "tenant_id": tenant_id,
            "version": version,
            "snapshot": snapshot,
            "updated_at": now,
        }


def get_behavior(tenant_id: str) -> dict[str, Any] | None:
    """Return the latest stored behavioral snapshot for *tenant_id* or ``None``."""
    _ensure_schema()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT version, snapshot, updated_at FROM twin_behavior "
            "WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "tenant_id": tenant_id,
        "version": int(row["version"]),
        "snapshot": json.loads(row["snapshot"]),
        "updated_at": row["updated_at"],
    }
