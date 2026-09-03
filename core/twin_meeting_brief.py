"""Meeting briefs from calendar events and repo context.

``render_meetings(tenant_id)`` produces a single local markdown page with one
section per upcoming calendar meeting, enriched with tracked repos and three
deterministic prep bullets.  No LLM, no network — pure computation over the
``twin_events``, ``twin_behavior`` tables.

The file is written under
``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/meeting_briefs.md``
and overwritten on each call.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.twin_behavior import get_behavior, rebuild
from core.twin_events import list_events
from core.twin_interview import get_latest_profile

_MAX_MEETINGS = 5


def _brief_path(tenant_id: str) -> Path:
    """Return the path to ``meeting_briefs.md`` for *tenant_id*."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id / "meeting_briefs.md"


def _collect_meetings(tenant_id: str) -> list[dict[str, str]]:
    """Collect up to ``_MAX_MEETINGS`` calendar meetings from twin_events."""
    meetings: list[dict[str, str]] = []
    for ev in list_events(tenant_id, limit=500):
        if ev.get("source") == "calendar" and ev.get("kind") == "meeting":
            payload = ev.get("payload") or {}
            meetings.append(
                {
                    "summary": str(payload.get("summary", "")),
                    "start": str(payload.get("start", "")),
                }
            )
            if len(meetings) >= _MAX_MEETINGS:
                break
    return meetings


def _collect_repos(tenant_id: str) -> list[str]:
    """Collect up to 8 repos from behavior snapshot or git event payloads."""
    behavior = get_behavior(tenant_id)
    repos: list[str] = []
    seen: set[str] = set()

    if behavior and behavior.get("snapshot"):
        for repo in behavior["snapshot"].get("repos", []) or []:
            if repo and repo not in seen:
                seen.add(repo)
                repos.append(str(repo))

    for ev in list_events(tenant_id, limit=500):
        payload = ev.get("payload") or {}
        repo = payload.get("repo") or payload.get("repo_name")
        if repo and repo not in seen:
            seen.add(repo)
            repos.append(str(repo))
            if len(repos) >= 8:
                break

    return repos


def _prep_bullets(meeting: dict[str, str], repos: list[str]) -> list[str]:
    """Return 3 deterministic prep bullets for *meeting*."""
    summary = meeting.get("summary") or "the meeting"
    repo_str = ", ".join(repos) if repos else "tracked repos"
    bullets: list[str] = [
        f"Review recent commits across {repo_str} before {summary}.",
        f"Prepare talking points for {summary}.",
        "Confirm the agenda and desired outcomes are circulated.",
    ]
    return bullets


def _render_markdown(
    tenant_id: str,
    meetings: list[dict[str, str]],
    repos: list[str],
) -> str:
    """Render the meeting briefs markdown content."""
    lines: list[str] = [
        f"# Meeting Briefs — {tenant_id}",
        "",
    ]
    if not meetings:
        lines.append("_No upcoming meetings._")
        lines.append("")
        return "\n".join(lines)

    for i, meeting in enumerate(meetings, start=1):
        summary = meeting["summary"] or "(untitled)"
        start = meeting["start"] or ""
        lines.append(f"## {i}. {summary}")
        lines.append("")
        if start:
            lines.append(f"**Start:** {start}")
            lines.append("")
        if repos:
            lines.append(f"**Repos:** {', '.join(repos)}")
        else:
            lines.append("**Repos:** _none tracked_")
        lines.append("")
        lines.append("**Prep:**")
        lines.append("")
        for bullet in _prep_bullets(meeting, repos):
            lines.append(f"- {bullet}")
        lines.append("")

    return "\n".join(lines)


def render_meetings(tenant_id: str) -> dict[str, Any]:
    """Render per-meeting briefs for *tenant_id*.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).

    If no behavioral snapshot exists yet, ``rebuild()`` is called first
    (safe — it is idempotent when already present).

    Collects up to 5 calendar meetings and tracked repos, writes
    ``meeting_briefs.md`` under ``work_products/{tenant_id}/``, and returns
    a dict with ``tenant_id``, ``path``, and ``count``.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    if get_behavior(tenant_id) is None:
        rebuild(tenant_id)

    meetings = _collect_meetings(tenant_id)
    repos = _collect_repos(tenant_id)

    content = _render_markdown(tenant_id, meetings, repos)

    out_path = _brief_path(tenant_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": out_path.as_posix(),
        "count": len(meetings),
    }
