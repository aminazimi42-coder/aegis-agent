"""Local ICS calendar ingest for the Aegis Agent platform.

Parses a local ``.ics`` file, extracts ``VEVENT`` blocks, and ingests each
well-formed event as a ``calendar`` / ``meeting`` twin event.  No external
calendar library is required — the parser is a small, dependency-free line
scanner.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.twin_events import ingest_event, list_events
from core.twin_evolution import evolve
from core.twin_interview import get_latest_profile

# ---------------------------------------------------------------------------#
# ICS parsing helpers
# ---------------------------------------------------------------------------#

_VEVENT_RE = re.compile(
    r"BEGIN:VEVENT(?P<body>.*?)END:VEVENT",
    re.DOTALL | re.IGNORECASE,
)


def _unescape(text: str) -> str:
    """Unescape ICS text values (commas, semicolons, newlines)."""
    return (
        text.replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\n", "\n")
        .replace("\\N", "\n")
        .strip()
    )


def _strip_params(line: str) -> tuple[str, str]:
    """Split a ``NAME;PARAM=val:VALUE`` line into (name, value)."""
    # Handle property parameters by finding the first colon.
    idx = line.find(":")
    if idx == -1:
        return line.strip(), ""
    name_part = line[:idx]
    value = line[idx + 1 :]
    # Strip any params from the name (e.g. DTSTART;TZID=...).
    semi_idx = name_part.find(";")
    if semi_idx != -1:
        name_part = name_part[:semi_idx]
    return name_part.strip().upper(), value.strip()


def _parse_vevent(block: str) -> dict[str, str] | None:
    """Parse a single VEVENT block; return {summary, start} or None if malformed."""
    summary: str | None = None
    start: str | None = None
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        name, value = _strip_params(line)
        if name == "SUMMARY":
            summary = _unescape(value)
        elif name == "DTSTART":
            start = value.strip()
    if summary is not None and start is not None:
        return {"summary": summary, "start": start}
    return None


# ---------------------------------------------------------------------------#
# Public API
# ---------------------------------------------------------------------------#

def ingest_ics(tenant_id: str, ics_path: str) -> dict[str, Any]:
    """Ingest a local ``.ics`` file as calendar events for ``tenant_id``.

    Requires a consented twin profile and an existing ``ics_path`` file.
    Each well-formed ``VEVENT`` with a ``SUMMARY`` and ``DTSTART`` is ingested
    as a ``calendar`` / ``meeting`` event and fed through the twin evolution
    loop.  Events are de-duplicated by ``(summary, start)`` against existing
    stored events for the tenant.

    Returns ``{"tenant_id": ..., "ingested": N, "skipped": M}``.
    """
    # Require a consented profile.
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    # Require the file to exist.
    if not Path(ics_path).is_file():
        raise ValueError("ics not found")

    # Read and parse the file.
    text = Path(ics_path).read_text(encoding="utf-8", errors="replace")

    # Collect existing (summary, start) pairs for dedup.
    existing: set[tuple[str, str]] = set()
    for ev in list_events(tenant_id, limit=500):
        payload = ev.get("payload") or {}
        ev_summary = payload.get("summary")
        ev_start = payload.get("start")
        if ev_summary is not None and ev_start is not None:
            existing.add((str(ev_summary), str(ev_start)))

    ingested = 0
    skipped = 0

    for match in _VEVENT_RE.finditer(text):
        block = match.group("body")
        parsed = _parse_vevent(block)
        if parsed is None:
            skipped += 1
            continue
        key = (parsed["summary"], parsed["start"])
        if key in existing:
            skipped += 1
            continue
        event = ingest_event(
            tenant_id=tenant_id,
            source="calendar",
            kind="meeting",
            payload={"summary": parsed["summary"], "start": parsed["start"]},
        )
        evolve(tenant_id, event)
        existing.add(key)
        ingested += 1

    return {
        "tenant_id": tenant_id,
        "ingested": ingested,
        "skipped": skipped,
    }
