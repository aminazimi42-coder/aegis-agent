"""Desk brief — render-only local brief writer (T118).

Reuses the T68 UTC scheduler.  ``render_brief_markdown(tenant_id)`` writes a
single markdown file under ``{AEGIS_DATA_DIR}/briefs/{tenant_id}/brief.md``.
No network, no LLM, no side effects beyond writing the local file.

``warn_if_stale()`` prints a local warning when the last scheduler tick is
older than 48 hours.  It is intended to be called on the next CLI/home load
and is *render-only* — it never sends network traffic or blocks.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_scheduler import list_jobs, tick

_STALE_THRESHOLD_HOURS = 48


def _briefs_dir(tenant_id: str) -> Path:
    """Return the directory for desk brief files."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "briefs" / tenant_id


def _last_tick_path() -> Path:
    """Return the path to the last-tick marker file."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "briefs" / ".last_tick"


def _now_iso() -> str:
    """Return the current UTC instant as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _render_markdown(tenant_id: str, due_jobs: list[dict[str, Any]]) -> str:
    """Render the desk brief markdown body."""
    now = _now_iso()
    lines: list[str] = [
        f"# Desk Brief — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
        "## Due commitments",
        "",
    ]
    if due_jobs:
        for job in due_jobs:
            title = job.get("title") or job.get("id") or "(untitled)"
            due_at = job.get("due_at") or ""
            lines.append(f"- {title}" + (f" — _{due_at}_" if due_at else ""))
    else:
        lines.append("_(none)_")
    lines.append("")
    return "\n".join(lines)


def render_brief_markdown(tenant_id: str) -> dict[str, Any]:
    """Write the local desk brief for *tenant_id* and return ``{tenant_id, path}``.

    Calls ``tick()`` from the T68 scheduler (render-only — no OS cron, no
    network) to collect due commitments, then writes a markdown file under
    ``{AEGIS_DATA_DIR}/briefs/{tenant_id}/brief.md``.

    Requires a consented twin profile (raised by ``tick`` indirectly when the
    schema is initialised).  No network calls are made.
    """
    due = tick()
    content = _render_markdown(tenant_id, due)

    out_dir = _briefs_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    brief_path = out_dir / "brief.md"
    brief_path.write_text(content, encoding="utf-8")

    # Record the tick so staleness can be detected later.
    _last_tick_path().parent.mkdir(parents=True, exist_ok=True)
    _last_tick_path().write_text(_now_iso(), encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": brief_path.as_posix(),
        "due_count": len(due),
    }


def _last_tick_iso() -> str | None:
    """Return the stored last-tick ISO string, or ``None`` if absent."""
    path = _last_tick_path()
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def warn_if_stale() -> str | None:
    """Return a local warning string when the last tick is older than 48 hours.

    Render-only — no network, no blocking.  Intended for CLI/home load.
    Returns ``None`` when there is no stale condition.
    """
    last = _last_tick_iso()
    if last is None:
        return None
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return None
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - last_dt
    if age.total_seconds() > _STALE_THRESHOLD_HOURS * 3600:
        return (
            f"warning: last desk tick was {age.days} days ago — "
            "run 'aegis tick' to refresh."
        )
    return None


def list_due(tenant_id: str) -> list[dict[str, Any]]:
    """Return due jobs for *tenant_id* (thin wrapper over T68 scheduler)."""
    return list_jobs(tenant_id, status="due")
