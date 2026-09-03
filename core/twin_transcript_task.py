"""T30 — Turn a local transcript .txt into one proposed twin action.

``from_transcript(tenant_id, transcript_path)`` reads a plain-text transcript
file, derives a short title from the first non-empty line (clipped to 80
characters), proposes a twin action with that title, and writes a markdown
work-product page recording the result.

No audio decode, no live network.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.persistence import get_connection
from core.twin_actions import _ensure_schema, _row_to_dict
from core.twin_interview import get_latest_profile

_MAX_TITLE = 80


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _derive_title(transcript_path: Path) -> str:
    """Extract the first non-empty line, stripped, clipped to 80 characters."""
    text = transcript_path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:_MAX_TITLE]
    return ""


def _insert_action(tenant_id: str, title: str) -> dict[str, Any]:
    """Insert a single proposed action with *title* and return it as a dict."""
    _ensure_schema()
    action_id = f"act-{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "action_id": action_id,
        "tenant_id": tenant_id,
        "kind": "transcript_task",
        "title": title,
        "status": "proposed",
        "created_at": now,
    }
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO twin_actions "
            "(action_id, tenant_id, kind, title, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                row["action_id"],
                row["tenant_id"],
                row["kind"],
                row["title"],
                row["status"],
                row["created_at"],
            ),
        )
    return _row_to_dict(row)


def from_transcript(tenant_id: str, transcript_path: str) -> dict[str, Any]:
    """Turn a local transcript .txt into one proposed twin action.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).  Requires *transcript_path* to be an existing
    file (raises ``ValueError("transcript not found")`` otherwise).

    Derives the title from the first non-empty line (stripped, clipped to
    80 characters), proposes a twin action via the existing propose API,
    writes ``work_products/{tenant_id}/transcript_task.md`` (overwriting
    any previous file), and returns
    ``{tenant_id, action_id, path, title}``.
    """
    # 1. Consent gate.
    if get_latest_profile(tenant_id) is None:
        raise ValueError("no consented profile")

    # 2. File gate.
    path = Path(transcript_path)
    if not path.is_file():
        raise ValueError("transcript not found")

    # 3. Derive title.
    title = _derive_title(path)

    # 4. Propose via the existing twin_actions propose API, then add a
    #    dedicated action with the transcript title.
    from core.twin_actions import propose_actions

    propose_actions(tenant_id)  # validates profile again; creates baseline actions
    action = _insert_action(tenant_id, title)

    # 5. Write markdown work-product.
    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "transcript_task.md"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# Transcript Task — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
        f"**Action ID:** {action['action_id']}",
        f"**Title:** {title}",
        f"**Status:** {action['status']}",
        "",
        "## Source",
        "",
        f"Transcript: `{transcript_path}`",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "action_id": action["action_id"],
        "path": str(md_path),
        "title": title,
    }
