"""Board weekly memo — one page a principal can paste into a board update.

``render_memo(tenant_id)`` produces a single markdown page that pulls
together the most relevant information for a board update:

- The first 40 lines of ``work_products/{tenant_id}/weekly_digest.md`` if
  that file already exists (otherwise the section is omitted).
- Up to 5 calendar meetings from ``twin_events``.
- Up to 5 repos from the behavioral snapshot and git-commit events.
- Up to 5 decisions from ``twin_decisions`` (imported defensively so the
  memo still renders if the decisions module is unavailable).
- The first 8 lines of ``work_products/{tenant_id}/style_lock.md`` under a
  ``Voice`` section if that file exists.

The file is written to
``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/board_memo.md``
and overwritten on each call.

No live LLM, no network calls — pure computation over local SQLite tables
and existing work-product files.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_behavior import get_behavior
from core.twin_events import list_events
from core.twin_interview import get_latest_profile

_MAX_MEETINGS = 5
_MAX_REPOS = 5
_MAX_DECISIONS = 5


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _read_weekly_digest(tenant_id: str) -> str:
    """Return the first 40 lines of ``weekly_digest.md`` if it exists."""
    path = _work_products_dir(tenant_id) / "weekly_digest.md"
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[:40])


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
    """Collect up to ``_MAX_REPOS`` repos from behavior snapshot and git events."""
    repos: list[str] = []
    seen: set[str] = set()

    behavior = get_behavior(tenant_id)
    if behavior and behavior.get("snapshot"):
        for repo in behavior["snapshot"].get("repos", []) or []:
            if repo and repo not in seen:
                seen.add(repo)
                repos.append(str(repo))
                if len(repos) >= _MAX_REPOS:
                    break

    if len(repos) < _MAX_REPOS:
        for ev in list_events(tenant_id, limit=500):
            payload = ev.get("payload") or {}
            repo = payload.get("repo") or payload.get("repo_name")
            if repo and repo not in seen:
                seen.add(repo)
                repos.append(str(repo))
                if len(repos) >= _MAX_REPOS:
                    break

    return repos


def _collect_decisions(tenant_id: str) -> list[dict[str, Any]]:
    """Collect up to ``_MAX_DECISIONS`` decisions, defensively."""
    try:
        from core.twin_decisions import list_decisions
    except ImportError:  # pragma: no cover — decisions module should exist
        return []
    try:
        decisions = list_decisions(tenant_id)
    except Exception:  # pragma: no cover — never let decisions break the memo
        return []
    return decisions[:_MAX_DECISIONS]


def _read_style_lock(tenant_id: str) -> str:
    """Return the first 8 lines of ``style_lock.md`` if it exists."""
    path = _work_products_dir(tenant_id) / "style_lock.md"
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[:8])


def _build_memo(
    tenant_id: str,
    digest_text: str,
    meetings: list[dict[str, str]],
    repos: list[str],
    decisions: list[dict[str, Any]],
    voice_text: str,
) -> str:
    """Render the ``board_memo.md`` content."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# Board Memo — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
    ]

    if digest_text:
        lines.append("## Weekly Digest")
        ""
        lines.append(digest_text)
        lines.append("")
    else:
        lines.append("## Weekly Digest")
        lines.append("")
        lines.append("_No weekly digest found._")
        lines.append("")

    lines.append("## Meetings")
    lines.append("")
    if meetings:
        for m in meetings:
            summary = m["summary"] or "(untitled)"
            start = m["start"] or ""
            if start:
                lines.append(f"- **{summary}** — {start}")
            else:
                lines.append(f"- **{summary}**")
    else:
        lines.append("_No upcoming meetings._")
    lines.append("")

    lines.append("## Repos")
    lines.append("")
    if repos:
        for repo in repos:
            lines.append(f"- {repo}")
    else:
        lines.append("_No tracked repos._")
    lines.append("")

    lines.append("## Decisions")
    lines.append("")
    if decisions:
        for d in decisions:
            title = d.get("title", "")
            decision_val = d.get("decision", "")
            reason = d.get("reason", "")
            entry = f"**{decision_val.upper()}** — {title}"
            if reason:
                entry += f" (_{reason}_)"
            lines.append(f"- {entry}")
    else:
        lines.append("_No decisions recorded._")
    lines.append("")

    if voice_text:
        lines.append("## Voice")
        lines.append("")
        lines.append(voice_text)
        lines.append("")

    lines.append("Do not act on this memo without written board approval.")
    lines.append("")
    return "\n".join(lines)


def render_memo(tenant_id: str) -> dict[str, Any]:
    """Render a one-page board memo for *tenant_id*.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).

    Prefers existing ``work_products/{tenant_id}/weekly_digest.md`` text
    (first 40 lines) if the file exists.  Always adds sections for Meetings
    (calendar up to 5), Repos (behavior/git up to 5), and Decisions
    (``list_decisions`` up to 5 if the import works).

    If ``style_lock.md`` exists, copies its first 8 lines under a ``Voice``
    section.

    Writes ``work_products/{tenant_id}/board_memo.md`` (overwriting any
    previous file) and returns ``{tenant_id, path}``.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    digest_text = _read_weekly_digest(tenant_id)
    meetings = _collect_meetings(tenant_id)
    repos = _collect_repos(tenant_id)
    decisions = _collect_decisions(tenant_id)
    voice_text = _read_style_lock(tenant_id)

    content = _build_memo(
        tenant_id,
        digest_text,
        meetings,
        repos,
        decisions,
        voice_text,
    )

    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "board_memo.md"
    out_path.write_text(content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": out_path.as_posix(),
    }
