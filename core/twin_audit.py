"""Hash-chained append-only audit log (T93).

Each successful *propose*, *approve*, or *execute* appends one JSON line to
``{data_root}/{tenant_id}/audit.jsonl``.  Lines form a SHA-256 hash chain:
each line's ``hash`` is the SHA-256 of the canonical JSON of that line's
fields **including** ``prev_hash`` but **excluding** ``hash`` itself.  The
first line's ``prev_hash`` is 64 zeros.  Earlier lines are never rewritten.

No network.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_ZERO_HASH = "0" * 64

_audit_lock = threading.Lock()


def _audit_path(tenant_id: str) -> Path:
    """Return the path to ``{data_root}/{tenant_id}/audit.jsonl``."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / tenant_id / "audit.jsonl"


def _last_hash(path: Path) -> str:
    """Return the ``hash`` of the last non-empty line, or 64 zeros."""
    if not path.is_file():
        return _ZERO_HASH
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            try:
                obj = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                return _ZERO_HASH
            return obj.get("hash", _ZERO_HASH)
    return _ZERO_HASH


def _compute_hash(ts: str, kind: str, action_id: str, prev_hash: str) -> str:
    """Return SHA-256 hex of the canonical line including ``prev_hash``."""
    canonical = json.dumps(
        {
            "ts": ts,
            "kind": kind,
            "action_id": action_id,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def append_audit(tenant_id: str, kind: str, action_id: str) -> str:
    """Append one audit line and return its ``hash``.

    ``kind`` must be ``"propose"``, ``"approve"``, or ``"execute"``.
    Creates the parent directory if needed.  Never rewrites earlier lines.
    """
    path = _audit_path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _audit_lock:
        prev_hash = _last_hash(path)
        ts = datetime.now(timezone.utc).isoformat()
        h = _compute_hash(ts, kind, action_id, prev_hash)
        line = json.dumps(
            {
                "ts": ts,
                "kind": kind,
                "action_id": action_id,
                "prev_hash": prev_hash,
                "hash": h,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    return h
