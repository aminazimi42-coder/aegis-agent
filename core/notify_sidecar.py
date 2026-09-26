"""T217 — Optional local notify sidecar.

After a successful Approve, an optional local notify sidecar may append
one line to ``AEGIS_DATA_DIR/notify/outbox.jsonl`` and return a typed
status.  The sidecar is **outside** the execute path — ``execute()`` and
``propose()`` never import this module and never call the network.

Behaviour
=========

* ``handle_approved_event(tenant_id, action_id, digest)`` writes one
  JSONL row when ``AEGIS_NOTIFY_WEBHOOK`` is set and non-empty.
  Otherwise it returns ``{"status": "not_configured"}`` — a typed
  skip, never an exception.

* The write is **local file only** in this slice.  An HTTP POST to the
  webhook is behind an explicit ``AEGIS_NOTIFY_HTTP=1`` flag.  Default
  is file-only so CI stays offline.

* Missing webhook / missing token is ``notify_not_configured``, not an
  exception.  A sidecar failure must not roll back the approval — the
  caller wraps the call in ``try/except`` and the action stays
  approved.

* Token / webhook values are redacted on audit like other secret
  shapes (see :mod:`core.redact`).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _webhook() -> str | None:
    """Return the configured webhook URL or ``None`` when unset."""
    val = os.environ.get("AEGIS_NOTIFY_WEBHOOK", "").strip()
    return val or None


def _http_enabled() -> bool:
    """Return ``True`` when ``AEGIS_NOTIFY_HTTP`` is set to ``1``."""
    return os.environ.get("AEGIS_NOTIFY_HTTP", "").strip() == "1"


def _outbox_path() -> Path:
    """Return the path to the local notify outbox JSONL file."""
    data_dir = os.environ.get("AEGIS_DATA_DIR", "data")
    return Path(data_dir) / "notify" / "outbox.jsonl"


def handle_approved_event(
    tenant_id: str,
    action_id: str,
    digest: str,
) -> dict[str, Any]:
    """Append one JSONL row for a successful Approve event.

    When ``AEGIS_NOTIFY_WEBHOOK`` is unset or empty, returns
    ``{"status": "not_configured"}`` without touching the filesystem.

    When the webhook is set and ``AEGIS_NOTIFY_HTTP`` is **not** ``1``
    (the default), writes one JSONL row to
    ``<AEGIS_DATA_DIR>/notify/outbox.jsonl`` and returns
    ``{"status": "file_written", "path": str}``.

    When ``AEGIS_NOTIFY_HTTP=1`` is set, the HTTP POST path would fire —
    but this slice keeps the default file-only behaviour so CI stays
    offline.  The HTTP flag is read but not exercised here.

    This function never raises.  A write failure returns
    ``{"status": "sidecar_failed"}`` — the caller's approval is not
    rolled back.
    """
    webhook = _webhook()
    if not webhook:
        return {"status": "not_configured"}

    row: dict[str, Any] = {
        "event": "approved",
        "tenant_id": tenant_id,
        "action_id": action_id,
        "digest": digest,
        "webhook": webhook,
        "http": _http_enabled(),
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    try:
        outbox = _outbox_path()
        outbox.parent.mkdir(parents=True, exist_ok=True)
        with open(outbox, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return {"status": "file_written", "path": str(outbox)}
    except Exception:
        return {"status": "sidecar_failed"}


def notify_status_label() -> str:
    """Return a one-line operator-page label for the notify sidecar.

    Returns ``"Notify file-only"`` when the webhook is set and HTTP is
    off, or ``"Notify not configured"`` when the webhook is unset.
    """
    if _webhook():
        return "Notify file-only"
    return "Notify not configured"
