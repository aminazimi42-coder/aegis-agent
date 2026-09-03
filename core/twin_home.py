"""Executive home page from real local state (T45).

``render_home(tenant_id)`` writes ``work_products/{tenant_id}/home.md`` — a
short page a busy principal can read in seconds: pending approvals, due
commitments, and a pointer to the morning brief when one exists.

Requires a consented twin profile and raises ``ValueError("no consented
profile")`` otherwise.  No live network calls, no LLM, no side effects beyond
writing the markdown file.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_interview import get_latest_profile
from core.twin_persist import list_approvals
from core.twin_scheduler import list_jobs
from core.twin_style_lock import apply_style


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _pending_approvals(tenant_id: str) -> list[dict[str, Any]]:
    """Return approvals for *tenant_id* whose status is ``pending``."""
    rows = list_approvals(tenant_id)
    return [r for r in rows if r.get("status") == "pending"]


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
    due: list[dict[str, Any]],
    brief_name: str | None,
) -> str:
    """Render the home page markdown body."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# Home — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
        "## Pending approvals",
        "",
    ]
    if pending:
        for item in pending:
            title = item.get("title") or item.get("id") or "(untitled)"
            lines.append(f"- {title}")
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

    return "\n".join(lines)


def render_home(tenant_id: str) -> dict[str, Any]:
    """Write ``home.md`` for *tenant_id* and return ``{tenant_id, path}``.

    Raises ``ValueError("no consented profile")`` when *tenant_id* has no
    committed profile.
    """
    if get_latest_profile(tenant_id) is None:
        raise ValueError("no consented profile")

    pending = _pending_approvals(tenant_id)
    due = _due_jobs(tenant_id)

    brief_path = _work_products_dir(tenant_id) / "morning_brief.md"
    brief_name = "morning_brief.md" if brief_path.exists() else None

    content = _render_markdown(tenant_id, pending, due, brief_name)
    content = apply_style(tenant_id, content)

    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    home_path = out_dir / "home.md"
    home_path.write_text(content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": home_path.as_posix(),
    }
