"""Morning one-page brief for the cognitive twin.

``render_brief(tenant_id)`` produces a single local markdown page a busy
principal can open first thing in the morning: today's calendar meetings,
recent repositories (from behavior snapshot or git event payloads), and
pending proposed/approved actions.  No LLM, no network — pure computation
over the ``twin_events``, ``twin_behavior``, and ``twin_actions`` tables.

The file is written under
``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/morning_brief.md``
and overwritten on each call.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.twin_actions import list_actions
from core.twin_behavior import get_behavior, rebuild
from core.twin_events import list_events
from core.twin_interview import get_latest_profile
from core.twin_style_lock import apply_style

_MAX_ITEMS = 8


def _brief_path(tenant_id: str) -> Path:
    """Return the path to ``morning_brief.md`` for *tenant_id*."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id / "morning_brief.md"


def _collect_meetings(tenant_id: str) -> list[dict[str, str]]:
    """Collect up to ``_MAX_ITEMS`` calendar meetings from twin_events."""
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
            if len(meetings) >= _MAX_ITEMS:
                break
    return meetings


def _collect_repos(tenant_id: str, behavior: dict[str, Any] | None) -> list[str]:
    """Collect up to ``_MAX_ITEMS`` repos from behavior snapshot or event payloads."""
    repos: list[str] = []
    seen: set[str] = set()

    # First, try the behavior snapshot.
    if behavior and behavior.get("snapshot"):
        for repo in behavior["snapshot"].get("repos", []) or []:
            if repo and repo not in seen:
                seen.add(repo)
                repos.append(repo)
                if len(repos) >= _MAX_ITEMS:
                    return repos

    # Fall back to scanning event payloads for repo fields.
    for ev in list_events(tenant_id, limit=500):
        payload = ev.get("payload") or {}
        repo = payload.get("repo") or payload.get("repo_name")
        if repo and repo not in seen:
            seen.add(repo)
            repos.append(str(repo))
            if len(repos) >= _MAX_ITEMS:
                break

    return repos


def _collect_pending_actions(tenant_id: str) -> list[dict[str, Any]]:
    """Collect up to ``_MAX_ITEMS`` actions with status proposed or approved."""
    pending: list[dict[str, Any]] = []
    for action in list_actions(tenant_id):
        if action.get("status") in {"proposed", "approved"}:
            pending.append(action)
            if len(pending) >= _MAX_ITEMS:
                break
    return pending


def _render_markdown(
    tenant_id: str,
    meetings: list[dict[str, str]],
    repos: list[str],
    pending_actions: list[dict[str, Any]],
) -> str:
    """Render the morning brief markdown content."""
    lines: list[str] = [
        f"# Morning Brief — {tenant_id}",
        "",
    ]

    # --- Meetings ---
    lines.append("## Meetings")
    lines.append("")
    if meetings:
        for m in meetings:
            summary = m["summary"] or "(untitled)"
            start = m["start"] or ""
            if start:
                lines.append(f"- {summary} — {start}")
            else:
                lines.append(f"- {summary}")
    else:
        lines.append("_No meetings scheduled today._")
    lines.append("")

    # --- Repos ---
    lines.append("## Repos")
    lines.append("")
    if repos:
        for repo in repos:
            lines.append(f"- {repo}")
    else:
        lines.append("_No recent repository activity._")
    lines.append("")

    # --- Pending actions ---
    lines.append("## Pending actions")
    lines.append("")
    if pending_actions:
        for action in pending_actions:
            title = action.get("title", "")
            status = action.get("status", "")
            lines.append(f"- [{status}] {title}")
    else:
        lines.append("_No pending actions._")
    lines.append("")

    return "\n".join(lines)


def render_brief(tenant_id: str) -> dict[str, Any]:
    """Render a one-page morning brief for *tenant_id*.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).

    If no behavioral snapshot exists yet, ``rebuild()`` is called first
    (safe — it is idempotent when already present).

    Collects meetings (calendar events), repos (from behavior snapshot or
    git event payloads), and pending actions (status ``proposed`` or
    ``approved``), writes ``morning_brief.md`` under
    ``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/``, and returns
    a dict with ``tenant_id``, ``path``, and ``sections``.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    # Ensure a behavioral snapshot exists (idempotent).
    if get_behavior(tenant_id) is None:
        rebuild(tenant_id)

    behavior = get_behavior(tenant_id)

    meetings = _collect_meetings(tenant_id)
    repos = _collect_repos(tenant_id, behavior)
    pending_actions = _collect_pending_actions(tenant_id)

    content = _render_markdown(tenant_id, meetings, repos, pending_actions)
    content = apply_style(tenant_id, content)

    brief_path = _brief_path(tenant_id)
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": brief_path.as_posix(),
        "sections": {
            "meetings": meetings,
            "repos": repos,
            "pending_actions": pending_actions,
        },
    }
