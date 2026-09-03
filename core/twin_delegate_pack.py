"""Delegate pack — one page a principal can hand to an assistant.

``render_pack(tenant_id)`` produces a single local markdown page that a busy
principal can hand to an assistant today.  It consolidates:

- **Meetings** — calendar events (up to 5)
- **Follow-ups** — email subjects (up to 8)
- **Pending actions** — proposed/approved twin actions (up to 8)
- **Repos** — from the behavioral snapshot or git event payloads (up to 5)

The page always carries the header:

    Do not send mail or move money without my written approval.

Deterministic, no LLM, no network — pure computation over the
``twin_events``, ``twin_behavior``, and ``twin_actions`` tables.

The file is written under
``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/delegate_pack.md``
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

_MAX_MEETINGS = 5
_MAX_FOLLOWUPS = 8
_MAX_ACTIONS = 8
_MAX_REPOS = 5


# ---------------------------------------------------------------------------#
# Path helpers
# ---------------------------------------------------------------------------#

def _pack_path(tenant_id: str) -> Path:
    """Return the path to ``delegate_pack.md`` for *tenant_id*."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id / "delegate_pack.md"


# ---------------------------------------------------------------------------#
# Section collectors
# ---------------------------------------------------------------------------#

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


def _collect_followups(tenant_id: str) -> list[str]:
    """Collect up to ``_MAX_FOLLOWUPS`` email subjects from twin_events."""
    subjects: list[str] = []
    seen: set[str] = set()
    for ev in list_events(tenant_id, limit=500):
        if ev.get("source") == "email" and ev.get("kind") == "message":
            payload = ev.get("payload") or {}
            subject = str(payload.get("subject", ""))
            if subject and subject not in seen:
                seen.add(subject)
                subjects.append(subject)
                if len(subjects) >= _MAX_FOLLOWUPS:
                    break
    return subjects


def _collect_pending_actions(tenant_id: str) -> list[dict[str, Any]]:
    """Collect up to ``_MAX_ACTIONS`` proposed/approved twin actions."""
    pending: list[dict[str, Any]] = []
    for action in list_actions(tenant_id):
        if action.get("status") in {"proposed", "approved"}:
            pending.append(action)
            if len(pending) >= _MAX_ACTIONS:
                break
    return pending


def _collect_repos(tenant_id: str, behavior: dict[str, Any] | None) -> list[str]:
    """Collect up to ``_MAX_REPOS`` repos from behavior snapshot or git payloads."""
    repos: list[str] = []
    seen: set[str] = set()

    # First, try the behavior snapshot.
    if behavior and behavior.get("snapshot"):
        for repo in behavior["snapshot"].get("repos", []) or []:
            if repo and repo not in seen:
                seen.add(repo)
                repos.append(str(repo))
                if len(repos) >= _MAX_REPOS:
                    return repos

    # Fall back to scanning event payloads for repo fields.
    for ev in list_events(tenant_id, limit=500):
        payload = ev.get("payload") or {}
        repo = payload.get("repo") or payload.get("repo_name")
        if repo and repo not in seen:
            seen.add(repo)
            repos.append(str(repo))
            if len(repos) >= _MAX_REPOS:
                break

    return repos


# ---------------------------------------------------------------------------#
# Markdown rendering
# ---------------------------------------------------------------------------#

def _render_markdown(
    tenant_id: str,
    meetings: list[dict[str, str]],
    followups: list[str],
    pending_actions: list[dict[str, Any]],
    repos: list[str],
) -> str:
    """Render the delegate-pack markdown content."""
    lines: list[str] = [
        f"# Delegate Pack — {tenant_id}",
        "",
        "> Do not send mail or move money without my written approval.",
        "",
    ]

    # --- Meetings --- #
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

    # --- Follow-ups --- #
    lines.append("## Follow-ups")
    lines.append("")
    if followups:
        for subject in followups:
            lines.append(f"- {subject}")
    else:
        lines.append("_No outstanding follow-ups._")
    lines.append("")

    # --- Pending actions --- #
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

    # --- Repos --- #
    lines.append("## Repos")
    lines.append("")
    if repos:
        for repo in repos:
            lines.append(f"- {repo}")
    else:
        lines.append("_No recent repository activity._")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#

def render_pack(tenant_id: str) -> dict[str, Any]:
    """Render a delegate pack for *tenant_id*.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).

    If no behavioral snapshot exists yet, ``rebuild()`` is called first
    (safe — it is idempotent when already present).

    Collects meetings (calendar events), follow-ups (email subjects), pending
    actions (status ``proposed`` or ``approved``), and repos (from behavior
    snapshot or git event payloads), writes ``delegate_pack.md`` under
    ``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/``, and returns
    a dict with ``tenant_id`` and ``path``.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    # Ensure a behavioral snapshot exists (idempotent).
    if get_behavior(tenant_id) is None:
        rebuild(tenant_id)

    behavior = get_behavior(tenant_id)

    meetings = _collect_meetings(tenant_id)
    followups = _collect_followups(tenant_id)
    pending_actions = _collect_pending_actions(tenant_id)
    repos = _collect_repos(tenant_id, behavior)

    content = _render_markdown(tenant_id, meetings, followups, pending_actions, repos)

    out_path = _pack_path(tenant_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": out_path.as_posix(),
    }
