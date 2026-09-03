"""Team inbox triage from a local chat export file.

``triage(tenant_id, export_path)`` reads a local team-chat export
(``.txt`` or ``.jsonl``) and writes a triage page
``work_products/{tenant_id}/team_inbox.md`` containing a numbered list of
up to 40 message lines.

*.txt* — one message per non-empty line.
*.jsonl* — each line is a JSON object with a ``text`` or ``body`` field.

No outbound send.  Overwrites the output file on each call.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.twin_events import ingest_event
from core.twin_interview import get_latest_profile

_MAX_LINES = 40


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _read_txt(path: Path) -> list[str]:
    """Return non-empty lines from a plain-text export."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _read_jsonl(path: Path) -> list[str]:
    """Return ``text`` or ``body`` values from a JSONL export."""
    messages: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = obj.get("text") or obj.get("body") or ""
        text = str(text).strip()
        if text:
            messages.append(text)
    return messages


def _build_team_inbox_md(tenant_id: str, messages: list[str]) -> str:
    """Render the ``team_inbox.md`` markdown content."""
    lines: list[str] = [
        f"# Team Inbox — {tenant_id}",
        "",
        f"**Message count:** {len(messages)}",
        "",
    ]
    for idx, msg in enumerate(messages[:_MAX_LINES], start=1):
        lines.append(f"{idx}. {msg}")
    lines.append("")
    return "\n".join(lines)


def triage(tenant_id: str, export_path: str) -> dict[str, Any]:
    """Triage a local team-chat export into a markdown page.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).  Requires *export_path* to be an existing file
    (raises ``ValueError("export not found")`` otherwise).

    Writes ``work_products/{tenant_id}/team_inbox.md`` (overwriting any
    previous file) and returns ``{tenant_id, path, count}``.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    path = Path(export_path)
    if not path.is_file():
        raise ValueError("export not found")

    if path.suffix.lower() == ".jsonl":
        messages = _read_jsonl(path)
    else:
        messages = _read_txt(path)

    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "team_inbox.md"
    out_path.write_text(
        _build_team_inbox_md(tenant_id, messages),
        encoding="utf-8",
    )

    # Best-effort event ingest — skip if the source/kind is rejected.
    try:
        ingest_event(
            tenant_id=tenant_id,
            source="chat",
            kind="message",
            payload={"count": len(messages)},
        )
    except ValueError:
        pass

    return {
        "tenant_id": tenant_id,
        "path": str(out_path),
        "count": len(messages),
    }
