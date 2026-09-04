"""Executive home page from real local state (T45/T58).

``render_home(tenant_id)`` writes ``work_products/{tenant_id}/home.md`` — a
short page a busy principal can read in seconds: pending twin_actions
(status ``proposed``), approved-but-not-executed actions, due
commitments, and a pointer to the morning brief when one exists.

The canonical operator queue is ``twin_actions`` — **not** the generic
``approvals`` table from ``twin_persist``.

Requires a consented twin profile and raises ``ValueError("no consented
profile")`` otherwise.  No live network calls, no LLM, no side effects beyond
writing the markdown file.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_actions import list_actions
from core.twin_interview import get_latest_profile
from core.twin_scheduler import list_jobs
from core.twin_style_lock import apply_style


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _pending_actions(tenant_id: str) -> list[dict[str, Any]]:
    """Return twin_actions rows for *tenant_id* whose status is ``proposed``."""
    return [a for a in list_actions(tenant_id) if a.get("status") == "proposed"]


def _approved_not_executed(tenant_id: str) -> list[dict[str, Any]]:
    """Return twin_actions rows for *tenant_id* that are approved but not yet executed."""
    return [a for a in list_actions(tenant_id) if a.get("status") == "approved"]


def _due_jobs(tenant_id: str) -> list[dict[str, Any]]:
    """Return scheduled jobs for *tenant_id* whose status is ``due``."""
    try:
        return list_jobs(tenant_id, status="due")
    except TypeError:
        # Fallback: list all then filter.
        return [j for j in list_jobs(tenant_id) if j.get("status") == "due"]


def _render_markdown(
    tenant_id: str,
    pending: list[dict[str, Any]],
    approved: list[dict[str, Any]],
    due: list[dict[str, Any]],
    brief_name: str | None,
    file_names: list[str],
) -> str:
    """Render the home page markdown body."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# Home — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
        "## Pending actions",
        "",
    ]
    if pending:
        for item in pending:
            action_id = item.get("action_id") or item.get("id") or ""
            title = item.get("title") or "(untitled)"
            risk = item.get("risk_level") or ""
            lines.append(f"- **{action_id}** — {title}" + (f" _(risk: {risk})_" if risk else ""))
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Approved — not yet executed")
    lines.append("")
    if approved:
        for item in approved:
            action_id = item.get("action_id") or item.get("id") or ""
            title = item.get("title") or "(untitled)"
            risk = item.get("risk_level") or ""
            lines.append(f"- **{action_id}** — {title}" + (f" _(risk: {risk})_" if risk else ""))
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Due commitments")
    lines.append("")
    if due:
        for item in due:
            title = item.get("title") or item.get("id") or "(untitled)"
            lines.append(f"- {title}")
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Brief")
    lines.append("")
    if brief_name:
        lines.append(f"See **{brief_name}** for today's morning brief.")
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Files")
    lines.append("")
    if file_names:
        for name in file_names:
            lines.append(f"- {name}")
    else:
        lines.append("(none)")
    lines.append("")

    return "\n".join(lines)


def render_home(tenant_id: str) -> dict[str, Any]:
    """Write ``home.md`` for *tenant_id* and return ``{tenant_id, path}``.

    Raises ``ValueError("no consented profile")`` when *tenant_id* has no
    committed profile.
    """
    if get_latest_profile(tenant_id) is None:
        raise ValueError("no consented profile")

    pending = _pending_actions(tenant_id)
    approved = _approved_not_executed(tenant_id)
    due = _due_jobs(tenant_id)

    brief_path = _work_products_dir(tenant_id) / "morning_brief.md"
    brief_name = "morning_brief.md" if brief_path.exists() else None

    out_dir = _work_products_dir(tenant_id)
    file_names: list[str] = []
    if out_dir.is_dir():
        file_names = sorted(
            f.name
            for f in out_dir.iterdir()
            if f.is_file() and f.name != "home.md"
        )

    content = _render_markdown(tenant_id, pending, approved, due, brief_name, file_names)
    content = apply_style(tenant_id, content)

    home_path = out_dir / "home.md"
    out_dir.mkdir(parents=True, exist_ok=True)
    home_path.write_text(content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": home_path.as_posix(),
    }
