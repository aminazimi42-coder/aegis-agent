"""Local session receipt — one JSON file per session under AEGIS_DATA_DIR.

T193 — after a successful propose, approve, or reject, a local session
receipt is written under ``<AEGIS_DATA_DIR>/receipts/session_<id>.json``.
No cloud.  No card numbers.  No payment fields.  The receipt is an audit
breadcrumb for this session only — not a month-long behavioral twin.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _engine_label() -> str:
    """Return the active engine label (``"echo"`` or ``"http"``)."""
    try:
        from core.llm_provider import get_provider

        provider = get_provider()
        return getattr(provider, "name", "echo")
    except Exception:
        return "echo"


def write_session_receipt(
    tenant_id: str,
    session_id: str | None = None,
    last_event: str = "propose",
    last_action_id: str = "",
    last_reject_reason: str = "",
) -> Path:
    """Write one local session receipt JSON under ``AEGIS_DATA_DIR/receipts/``.

    T193 — the receipt is an audit breadcrumb for this session only.
    No cloud, no card numbers, no payment fields.

    The file path is ``<AEGIS_DATA_DIR>/receipts/session_<id>.json``
    where ``<id>`` is the session id or the tenant id when no session id
    is available.  The T190 path cage stays in force — a path outside
    ``AEGIS_DATA_DIR`` raises :class:`~core.twin_local_view.PathDeniedError`
    and does not write.
    """
    from core.twin_local_view import cage_path, data_root

    root = data_root()
    sid = session_id or tenant_id
    receipts_dir = root / "receipts"
    receipts_dir = cage_path(receipts_dir)
    receipts_dir.mkdir(parents=True, exist_ok=True)

    receipt_path = receipts_dir / f"session_{sid}.json"
    receipt_path = cage_path(receipt_path)

    receipt: dict[str, Any] = {
        "tenant_id": tenant_id,
        "session_id": sid,
        "last_event": last_event,
        "last_action_id": last_action_id,
        "last_reject_reason": last_reject_reason,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "engine": _engine_label(),
    }

    receipt_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return receipt_path
