"""Follow-up list from email and meeting events.

``render_followups(tenant_id)`` produces a single local markdown page listing
the items a busy principal still owes a response to — emails that need a reply
and meetings that need a follow-up.  Deterministic, no LLM, no network.

Items are derived from ``twin_events``:
  - ``source=email kind=message`` → follow-up on the email subject
  - ``source=calendar kind=meeting`` → follow-up after the meeting summary

Deduplicated by ``(source, subject_or_summary)`` and written to
``work_products/{tenant_id}/follow_ups.md`` (overwritten on each call).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.twin_interview import get_latest_profile


def _followups_path(tenant_id: str) -> Path:
    """Return the path to ``follow_ups.md`` for *tenant_id*."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id / "follow_ups.md"


def _collect_followups(tenant_id: str) -> list[dict[str, str]]:
    """Collect deduplicated follow-up items from twin_events."""
    from core.twin_events import list_events

    seen: set[tuple[str, str]] = set()
    items: list[dict[str, str]] = []

    for ev in list_events(tenant_id, limit=500):
        source = ev.get("source", "")
        kind = ev.get("kind", "")
        payload = ev.get("payload") or {}

        if source == "email" and kind == "message":
            subject = str(payload.get("subject", ""))
            key = ("email", subject)
            if key in seen or not subject:
                continue
            seen.add(key)
            items.append(
                {
                    "source": "email",
                    "label": subject,
                    "detail": f"Reply to email: {subject}",
                }
            )
        elif source == "calendar" and kind == "meeting":
            summary = str(payload.get("summary", ""))
            key = ("calendar", summary)
            if key in seen or not summary:
                continue
            seen.add(key)
            items.append(
                {
                    "source": "calendar",
                    "label": summary,
                    "detail": f"Follow up after meeting: {summary}",
                }
            )

    return items


def _render_markdown(tenant_id: str, items: list[dict[str, str]]) -> str:
    """Render the follow-ups markdown content."""
    lines: list[str] = [
        f"# Follow-ups — {tenant_id}",
        "",
    ]
    if not items:
        lines.append("_No outstanding follow-ups._")
        lines.append("")
        return "\n".join(lines)

    for i, item in enumerate(items, start=1):
        lines.append(f"{i}. {item['detail']}")
    lines.append("")

    return "\n".join(lines)


def render_followups(tenant_id: str) -> dict[str, Any]:
    """Render a follow-up list for *tenant_id*.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).

    Collects follow-up items from email messages and calendar meetings in
    ``twin_events``, deduplicates by ``(source, subject_or_summary)``,
    writes ``follow_ups.md`` under ``work_products/{tenant_id}/``, and
    returns ``{"tenant_id": ..., "path": ..., "count": N}``.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    items = _collect_followups(tenant_id)

    content = _render_markdown(tenant_id, items)

    out_path = _followups_path(tenant_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "path": out_path.as_posix(),
        "count": len(items),
    }
