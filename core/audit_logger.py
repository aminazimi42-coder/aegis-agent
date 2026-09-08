"""JSONL audit logger (T118).

One JSON object per propose/approve/reject/execute/purge/replay cycle
event, written under ``{AEGIS_DATA_DIR}/audit/YYYY-MM-DD.jsonl``.

Each line shares a ``correlation_id`` across one ``action_id``.  No
telemetry egress — the file is local only.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

_audit_lock = threading.Lock()

_VALID_KINDS: frozenset[str] = frozenset(
    {"propose", "approve", "reject", "execute", "purge", "replay"}
)

# Map action_id → correlation_id so all events for one action share a
# correlation id within a process.
_correlation_map: dict[str, str] = {}


def _audit_dir() -> Path:
    """Return the audit directory under ``AEGIS_DATA_DIR``."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "audit"


def _audit_path(date_str: str | None = None) -> Path:
    """Return the path to the audit JSONL file for *date_str* (UTC date)."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _audit_dir() / f"{date_str}.jsonl"


def _get_or_create_correlation(action_id: str) -> str:
    """Return the correlation_id for *action_id*, creating one if needed."""
    if action_id not in _correlation_map:
        _correlation_map[action_id] = uuid4().hex
    return _correlation_map[action_id]


def log_event(
    kind: str,
    action_id: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one JSONL audit line and return the event dict.

    ``kind`` must be one of ``propose``, ``approve``, ``reject``,
    ``execute``, ``purge``, ``replay``.  The line contains:
    ``ts``, ``kind``, ``action_id``, ``correlation_id``.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(f"invalid audit kind: {kind}")

    ts = datetime.now(timezone.utc).isoformat()
    correlation_id = _get_or_create_correlation(action_id)
    event: dict[str, Any] = {
        "ts": ts,
        "kind": kind,
        "action_id": action_id,
        "correlation_id": correlation_id,
    }
    if extra:
        # T124 — redact secret-shaped strings from audit extra values.
        from core.redact import redact_payload

        event.update(redact_payload(extra))

    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        event,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    with _audit_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    return event


def read_events(path: str | None = None) -> list[dict[str, Any]]:
    """Read and parse all audit lines from *path* (defaults to today's file)."""
    target = Path(path) if path else _audit_path()
    if not target.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            events.append(json.loads(stripped))
        except (json.JSONDecodeError, ValueError):
            continue
    return events


def get_correlation_id(action_id: str) -> str | None:
    """Return the correlation_id for *action_id* or ``None`` if unset."""
    return _correlation_map.get(action_id)
