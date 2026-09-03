"""Travel pack — one-page trip summary from calendar events and local docs.

``render_pack(tenant_id, docs_dir="")`` collects calendar meetings whose
summary mentions flight/hotel/travel, lists documents from a local docs
folder (names only — never contents), and writes a single
``travel_pack.md`` page under
``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/``.

No live LLM, no network calls.  Overwrites the output on each call.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_events import list_events
from core.twin_interview import get_latest_profile

_TRAVEL_KEYWORDS = ("flight", "hotel", "travel")
_DOC_SUFFIXES = (".pdf", ".txt", ".md")


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _collect_travel_meetings(tenant_id: str) -> list[dict[str, Any]]:
    """Return calendar meetings whose summary mentions a travel keyword."""
    meetings: list[dict[str, Any]] = []
    for ev in list_events(tenant_id, limit=1000):
        if ev.get("source") != "calendar" or ev.get("kind") != "meeting":
            continue
        payload = ev.get("payload") or {}
        summary = str(payload.get("summary") or "")
        if any(kw in summary.lower() for kw in _TRAVEL_KEYWORDS):
            meetings.append(
                {
                    "summary": summary,
                    "start": str(payload.get("start") or ""),
                }
            )
    return meetings


def _list_docs(docs_dir: str) -> list[str]:
    """Return sorted file names (not contents) for supported doc types."""
    d = Path(docs_dir)
    if not d.is_dir():
        return []
    names: list[str] = []
    for p in sorted(d.iterdir()):
        if p.is_file() and p.suffix.lower() in _DOC_SUFFIXES:
            names.append(p.name)
    return names


def _build_travel_pack(
    tenant_id: str,
    meetings: list[dict[str, Any]],
    docs: list[str],
    docs_dir: str,
) -> str:
    """Render the ``travel_pack.md`` content."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# Travel Pack — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
        "## Itinerary",
        "",
    ]
    if meetings:
        for m in meetings:
            lines.append(f"- **{m['summary']}** — {m['start']}")
    else:
        lines.append("_No travel meetings found._")
    lines.append("")

    lines.append("## Documents")
    ""
    if docs_dir:
        lines.append(f"_Source dir: {docs_dir}_")
        lines.append("")
    if docs:
        for name in docs:
            lines.append(f"- {name}")
    else:
        lines.append("_No documents found._")
    lines.append("")

    lines.append("Do not book or pay without written approval.")
    lines.append("")
    return "\n".join(lines)


def render_pack(tenant_id: str, docs_dir: str = "") -> dict[str, Any]:
    """Render a one-page travel pack for *tenant_id*.

    Collects calendar meetings whose summary contains ``flight``,
    ``hotel``, or ``travel`` and — if *docs_dir* is an existing
    directory — lists ``*.pdf``, ``*.txt``, and ``*.md`` file names
    (never contents).

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).

    Writes ``work_products/{tenant_id}/travel_pack.md`` (overwriting any
    previous file) and returns ``{tenant_id, path}``.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    meetings = _collect_travel_meetings(tenant_id)
    docs = _list_docs(docs_dir) if docs_dir else []

    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "travel_pack.md"
    out_path.write_text(
        _build_travel_pack(tenant_id, meetings, docs, docs_dir),
        encoding="utf-8",
    )

    return {
        "tenant_id": tenant_id,
        "path": out_path.as_posix(),
    }
