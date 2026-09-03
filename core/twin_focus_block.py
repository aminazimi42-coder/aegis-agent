"""Local focus-block hold — markdown + iCalendar for a principal's calendar.

``create_block(tenant_id, start, ...)`` produces two local files a CTO can
drop into a calendar:

* ``focus_block.md`` — a human-readable summary of the block.
* ``focus_block.ics`` — a single ``VEVENT`` calendar entry.

No cloud calendar integration — files are written under
``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/`` and overwritten on
each call.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.twin_interview import get_latest_profile


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where focus-block files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _focus_block_md(
    tenant_id: str,
    title: str,
    start: str,
    duration_min: int,
) -> str:
    """Render the focus-block markdown content."""
    lines: list[str] = [
        f"# {title} — {tenant_id}",
        "",
        f"- **Start:** {start}",
        f"- **Duration:** {duration_min} minutes",
        "",
        "_Hold this block on your calendar — no meetings, no interruptions._",
        "",
    ]
    return "\n".join(lines)


def _focus_block_ics(
    tenant_id: str,
    title: str,
    start: str,
    duration_min: int,
) -> str:
    """Render a minimal single-VEVENT iCalendar payload."""
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Aegis//Focus Block//EN",
        "BEGIN:VEVENT",
        f"UID:focus-{tenant_id}-{start}@aegis",
        f"SUMMARY:{title}",
        f"DTSTART:{start}",
        f"DURATION:PT{duration_min}M",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ]
    return "\n".join(lines)


def create_block(
    tenant_id: str,
    start: str,
    duration_min: int = 90,
    title: str = "Focus",
) -> dict[str, Any]:
    """Create a local focus-block hold (markdown + .ics) for *tenant_id*.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise).

    *duration_min* must be an ``int`` >= 15 (raises ``ValueError("invalid
    duration")`` otherwise).

    Writes ``focus_block.md`` and ``focus_block.ics`` under
    ``{AEGIS_DATA_DIR or ./data}/work_products/{tenant_id}/`` and returns a
    dict with ``tenant_id``, ``path_md``, and ``path_ics`` (absolute paths).
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    if not isinstance(duration_min, int) or duration_min < 15:
        raise ValueError("invalid duration")

    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / "focus_block.md"
    ics_path = out_dir / "focus_block.ics"

    md_path.write_text(
        _focus_block_md(tenant_id, title, start, duration_min),
        encoding="utf-8",
    )
    ics_path.write_text(
        _focus_block_ics(tenant_id, title, start, duration_min),
        encoding="utf-8",
    )

    return {
        "tenant_id": tenant_id,
        "path_md": md_path.as_posix(),
        "path_ics": ics_path.as_posix(),
    }
