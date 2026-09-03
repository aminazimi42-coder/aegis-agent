"""T33 — Send an approved email draft to a local outbox only.

``send_approved(tenant_id, action_id)`` copies the draft text from a
human-approved twin action into ``work_products/{tenant_id}/outbox/`` as an
``.eml`` file.  No network send, no socket — the file is the outbox.

The action must have a consented profile (``ValueError("no consented
profile")`` if missing), must exist (``ValueError("action not found")`` if
missing), and must be in the ``approved`` status (``ValueError("not
approved")`` otherwise).

The ``.eml`` file includes a header line ``X-Aegis-Send:
local-outbox-only`` to mark it as local-only.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.twin_actions import _ensure_schema, _load_action
from core.twin_interview import get_latest_profile


def _work_products_dir(tenant_id: str) -> Path:
    """Return the work-products base directory for *tenant_id*."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _outbox_dir(tenant_id: str) -> Path:
    """Return the outbox directory for *tenant_id*."""
    return _work_products_dir(tenant_id) / "outbox"


def send_approved(tenant_id: str, action_id: str) -> dict[str, Any]:
    """Copy an approved email draft into the local outbox.

    Requires a consented profile (otherwise ``ValueError("no consented
    profile")`` is raised).  The action must exist (``ValueError("action
    not found")``) and be in the ``approved`` status
    (``ValueError("not approved")``).

    Writes ``work_products/{tenant_id}/outbox/{action_id}.eml`` with the
    subject from the action title and body from the action payload (if
    available, otherwise the title).  The file always includes the header
    line ``X-Aegis-Send: local-outbox-only``.

    Returns ``{tenant_id, path, action_id}``.
    """
    # 1. Consent gate.
    if get_latest_profile(tenant_id) is None:
        raise ValueError("no consented profile")

    # 2. Action gate.
    _ensure_schema()
    action = _load_action(action_id)
    if action is None:
        raise ValueError("action not found")

    # 3. Approval gate.
    if action["status"] != "approved":
        raise ValueError("not approved")

    # 4. Derive subject and body from the action.
    subject = action.get("title", "")
    body = action.get("payload") if isinstance(action.get("payload"), str) else subject

    # 5. Write .eml file to the local outbox (no socket, no network).
    out_dir = _outbox_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    eml_path = out_dir / f"{action_id}.eml"

    lines = [
        "X-Aegis-Send: local-outbox-only",
        f"Subject: {subject}",
        "",
        body,
    ]
    eml_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": str(eml_path),
        "action_id": action_id,
    }
