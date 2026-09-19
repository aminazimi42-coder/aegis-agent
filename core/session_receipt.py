"""Local session receipt — one JSON file per session under AEGIS_DATA_DIR.

T193 — after a successful propose, approve, or reject, a local session
receipt is written under ``<AEGIS_DATA_DIR>/receipts/session_<id>.json``.
No cloud.  No card numbers.  No payment fields.  The receipt is an audit
breadcrumb for this session only — not a month-long behavioral twin.

T203 — the receipt also stores ``last_task`` (the task text that produced
the last propose batch) so a new Start Session on the same data dir after
an engine sleep restores the prior session id and the last task string.
``read_session_receipt(tenant_id)`` reads the prior receipt; the Start
Session route returns the prior session id when a receipt exists.
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
    last_task: str = "",
    quiet_mode: bool | None = None,
) -> Path:
    """Write one local session receipt JSON under ``AEGIS_DATA_DIR/receipts/``.

    T193 — the receipt is an audit breadcrumb for this session only.
    No cloud, no card numbers, no payment fields.

    T203 — ``last_task`` is the operator task text that produced the last
    propose batch, so a new Start Session on the same data dir after an
    engine sleep can restore it.

    T207 — ``quiet_mode`` is the Quiet-mode flag for this tenant.  When
    ``None`` the existing flag is preserved (refresh does not clear it);
    when ``True`` or ``False`` the flag is written and persisted.

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

    # T207 — preserve the existing quiet_mode when the caller does not
    # pass an explicit value (refresh alone does not clear Quiet).
    existing_quiet = False
    if receipt_path.is_file():
        try:
            prev = json.loads(receipt_path.read_text(encoding="utf-8"))
            if isinstance(prev, dict) and isinstance(prev.get("quiet_mode"), bool):
                existing_quiet = prev["quiet_mode"]
        except (OSError, ValueError, TypeError):
            pass
    effective_quiet = existing_quiet if quiet_mode is None else quiet_mode

    receipt: dict[str, Any] = {
        "tenant_id": tenant_id,
        "session_id": sid,
        "last_event": last_event,
        "last_action_id": last_action_id,
        "last_reject_reason": last_reject_reason,
        "last_task": last_task,
        "quiet_mode": effective_quiet,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "engine": _engine_label(),
    }

    receipt_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return receipt_path


def read_session_receipt(tenant_id: str) -> dict[str, Any] | None:
    """Read the prior session receipt for *tenant_id*.

    T203 — returns ``None`` when the receipt is missing or unreadable.
    The caller (Start Session route) uses the returned ``session_id`` and
    ``last_task`` to restore the prior session after an engine sleep.

    T207 — the receipt also stores ``quiet_mode`` so the propose path
    can check whether Quiet is on for this tenant without a second
    read.
    """
    from core.twin_local_view import data_root

    root = data_root()
    receipts_dir = root / "receipts"
    # Try the tenant-named receipt first, then fall back to any
    # session_*.json whose tenant_id matches.
    candidates: list[Path] = [receipts_dir / f"session_{tenant_id}.json"]
    try:
        for p in receipts_dir.glob("session_*.json"):
            if p not in candidates:
                candidates.append(p)
    except OSError:
        pass
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("tenant_id") == tenant_id:
            return data
    return None


def is_quiet_mode(tenant_id: str) -> bool:
    """Return ``True`` when Quiet mode is on for *tenant_id*.

    T207 — reads the local session receipt under
    ``AEGIS_DATA_DIR/receipts/`` and returns the ``quiet_mode`` field.
    When the receipt is missing or the field is absent, returns
    ``False`` (Quiet is off by default).  Neighbor tenants are not
    scanned — the flag is tenant-bound.
    """
    receipt = read_session_receipt(tenant_id)
    if receipt is None:
        return False
    return bool(receipt.get("quiet_mode", False))


def set_quiet_mode(tenant_id: str, quiet: bool) -> None:
    """Set the Quiet-mode flag for *tenant_id* on the session receipt.

    T207 — writes ``quiet_mode`` on the durable local session receipt
    under ``AEGIS_DATA_DIR/receipts/``.  The flag is tenant-bound: a
    neighbor tenant's Quiet does not apply.
    """
    receipt = read_session_receipt(tenant_id)
    session_id = receipt.get("session_id") if receipt else None
    last_event = receipt.get("last_event", "propose") if receipt else "propose"
    last_action_id = receipt.get("last_action_id", "") if receipt else ""
    last_reject_reason = receipt.get("last_reject_reason", "") if receipt else ""
    last_task = receipt.get("last_task", "") if receipt else ""
    write_session_receipt(
        tenant_id,
        session_id=session_id,
        last_event=last_event,
        last_action_id=last_action_id,
        last_reject_reason=last_reject_reason,
        last_task=last_task,
        quiet_mode=quiet,
    )
