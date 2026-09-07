"""T102 — Local guards: dead-man, overlap, duplicate, inbox score, transcript gap, delegate close.

Six zero-network, detection-only local guards for the Aegis Agent platform.
None of these auto-send mail, auto-resolve, or perform any side effect — they
only **warn** and **flag**.

Guards:

1. **Dead-man** — ``dead_man_warning(tenant_id)`` returns a warning string
   when the last scheduler tick is older than 48 hours (or the tick file
   is missing), so the next ``aegis status`` print can surface it.

2. **Focus-block overlap** — ``check_overlap(tenant_id, title, start, duration_min)``
   returns ``{"overlap": bool, "conflict": bool, ...}`` when a proposed
   time slot overlaps a local ``.ics`` calendar event.  Still propose-only.

3. **Expense duplicate** — ``flag_expense_duplicates(tenant_id, receipts)``
   returns a list of receipt dicts where two receipts sharing the same
   ``amount``, ``vendor``, and ``date`` get ``duplicate=True``.

4. **Inbox score** — ``inbox_score(tenant_id, text)`` scores a message
   using Day-0 profile keywords only — no cloud model, no network.

5. **Transcript gap** — ``transcript_confidence(tenant_id, transcript_path)``
   returns ``"low"`` when a transcript source file has missing/empty text,
   so proposed actions from it get ``confidence=low``.

6. **Delegate close** — ``delegate_close_link(tenant_id, decision_title)``
   when a decision-record marks a delegate item done, writes a local link
   back to the pack file if present.

No live network.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_local_view import data_root

_DEAD_MAN_HOURS = 48


# ---------------------------------------------------------------------------#
# Path helpers
# ---------------------------------------------------------------------------#


def _work_products_dir(tenant_id: str) -> Path:
    """Return the work-products directory for *tenant_id*."""
    return data_root() / "work_products" / tenant_id


def _tick_path(tenant_id: str) -> Path:
    """Return the path to the scheduler tick marker file."""
    return data_root() / tenant_id / "last_tick.json"


# ---------------------------------------------------------------------------#
# 1) Dead-man guard
# ---------------------------------------------------------------------------#


def record_tick(tenant_id: str) -> str:
    """Write a ``last_tick.json`` marker with the current UTC timestamp.

    Returns the ISO-8601 timestamp written.  No network.
    """
    now = datetime.now(timezone.utc).isoformat()
    path = _tick_path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'{{"tenant_id": "{tenant_id}", "tick_at": "{now}"}}',
        encoding="utf-8",
    )
    return now


def _last_tick_time(tenant_id: str) -> datetime | None:
    """Return the last tick datetime for *tenant_id*, or ``None`` when missing/unparseable."""
    path = _tick_path(tenant_id)
    if not path.is_file():
        return None
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        ts = data.get("tick_at") or data.get("ts")
        if not ts:
            return None
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (OSError, ValueError, TypeError):
        return None


def dead_man_warning(tenant_id: str, now: datetime | None = None) -> str:
    """Return a warning string when the scheduler dead-man switch triggers.

    Returns a non-empty warning line when the last tick is older than 48
    hours, or when the tick marker file is missing entirely.  Returns an
    empty string when the tick is recent enough.

    No network.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    last = _last_tick_time(tenant_id)
    if last is None:
        return (
            f"dead-man: no scheduler tick recorded for tenant "
            f"{tenant_id!r} — last tick file missing"
        )

    age_hours = (now - last).total_seconds() / 3600.0
    if age_hours > _DEAD_MAN_HOURS:
        return (
            f"dead-man: last scheduler tick for tenant {tenant_id!r} "
            f"was {age_hours:.1f}h ago (>{_DEAD_MAN_HOURS}h)"
        )
    return ""


# ---------------------------------------------------------------------------#
# 2) Focus-block overlap guard
# ---------------------------------------------------------------------------#


def _parse_ics_datetime(value: str) -> datetime | None:
    """Parse an ICS ``DTSTART`` value into a UTC datetime, or ``None``.

    Accepts both ICS compact format (``20250615T100000Z``) and ISO-8601
    (``2025-06-15T10:00:00`` or ``2025-06-15T10:00:00Z``).  When the value
    contains a TZID parameter prefix (``...;TZID=...:VALUE``), the part
    after the last ``;``/``:`` separator is used.
    """
    value = value.strip()
    # Strip ``KEY;PARAM=val:VALUE`` — only when there's a ``;`` parameter.
    if ";" in value:
        value = value.rsplit(":", 1)[-1]
    # Try ISO-8601 first (handles colons in the time portion).
    iso_candidate = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(iso_candidate)
    except ValueError:
        # Fall back to ICS basic format YYYYMMDDTHHMMSS.
        try:
            dt = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        except (ValueError, IndexError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_local_ics(tenant_id: str) -> list[dict[str, str]]:
    """Parse the local focus-block ``.ics`` file for *tenant_id* into event dicts."""
    ics_path = _work_products_dir(tenant_id) / "focus_block.ics"
    if not ics_path.is_file():
        return []

    text = ics_path.read_text(encoding="utf-8", errors="replace")
    events: list[dict[str, str]] = []
    vevent_re = re.compile(
        r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL | re.IGNORECASE,
    )
    for match in vevent_re.finditer(text):
        block = match.group(1)
        summary = ""
        dtstart = ""
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            idx = line.find(":")
            if idx == -1:
                continue
            name = line[:idx].split(";")[0].strip().upper()
            value = line[idx + 1:].strip()
            if name == "SUMMARY":
                summary = value
            elif name == "DTSTART":
                dtstart = value
        if dtstart:
            events.append({"summary": summary, "start": dtstart})
    return events


def _parse_propose_time(title: str, payload: Any) -> str:
    """Extract a datetime string from a propose title or payload."""
    # Look for an ISO-like date in the title.
    match = re.search(r"\d{4}-\d{2}-\d{2}[T ]?\d{2}[:.]?\d{2}", str(title))
    if match:
        return match.group(0)
    if isinstance(payload, dict):
        for key in ("start", "dtstart", "time", "when", "slot"):
            val = payload.get(key)
            if val:
                return str(val)
    return ""


def check_overlap(
    tenant_id: str,
    title: str = "",
    start: str = "",
    duration_min: int = 90,
    payload: Any = None,
) -> dict[str, Any]:
    """Check whether a proposed time slot overlaps a local ``.ics`` event.

    Returns a dict with ``overlap`` (bool) and ``conflict`` (bool) keys.
    ``overlap`` is ``True`` when the proposed slot intersects a local
    calendar event; ``conflict`` mirrors it as the conflict flag name.
    Still propose-only — never auto-resolves or blocks.
    """
    proposed_start_str = start or _parse_propose_time(title, payload)
    proposed_start = _parse_ics_datetime(proposed_start_str)
    if proposed_start is None:
        return {"overlap": False, "conflict": False, "reason": "no time slot in propose"}

    from datetime import timedelta

    proposed_end = proposed_start + timedelta(minutes=max(15, duration_min))

    events = _parse_local_ics(tenant_id)
    for ev in events:
        ev_start = _parse_ics_datetime(ev.get("start", ""))
        if ev_start is None:
            continue
        # Assume 60-minute default for ICS events without a DURATION.
        ev_end = ev_start + timedelta(minutes=60)
        if proposed_start < ev_end and ev_start < proposed_end:
            return {
                "overlap": True,
                "conflict": True,
                "event": ev.get("summary", ""),
                "event_start": ev.get("start", ""),
            }
    return {"overlap": False, "conflict": False}


# ---------------------------------------------------------------------------#
# 3) Expense duplicate guard
# ---------------------------------------------------------------------------#


def _receipt_key(receipt: dict[str, Any]) -> tuple[str, str, str]:
    """Return the ``(amount, vendor, date)`` dedup key for a receipt dict."""
    return (
        str(receipt.get("amount", "")),
        str(receipt.get("vendor", "")),
        str(receipt.get("date", "")),
    )


def flag_expense_duplicates(
    tenant_id: str,  # noqa: ARG001 — kept for API symmetry
    receipts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flag expense receipts that share the same amount+vendor+date.

    Returns the same list of receipts (not modified in place) with a
    ``duplicate`` boolean key added: ``True`` when another receipt in
    the list shares the same ``(amount, vendor, date)`` triple.

    Detection only — does not dedupe, delete, or auto-resolve.
    """
    counts: dict[tuple[str, str, str], int] = {}
    for r in receipts:
        key = _receipt_key(r)
        counts[key] = counts.get(key, 0) + 1

    result: list[dict[str, Any]] = []
    for r in receipts:
        key = _receipt_key(r)
        dup = counts.get(key, 0) > 1
        result.append({**r, "duplicate": dup})
    return result


# ---------------------------------------------------------------------------#
# 4) Inbox score (Day-0 profile keywords only)
# ---------------------------------------------------------------------------#


def _profile_keywords(tenant_id: str) -> list[str]:
    """Return lower-case keywords from the Day-0 profile for *tenant_id*.

    Reads ``{data_root}/{tenant_id}/profile.json`` and extracts values from
    ``role``, ``goal``, and any ``keywords`` list.  Falls back to the
    SQLite-backed profile when the local file is missing.
    """
    keywords: list[str] = []

    local_profile = data_root() / tenant_id / "profile.json"
    if local_profile.is_file():
        try:
            import json

            data = json.loads(local_profile.read_text(encoding="utf-8"))
            for key in ("role", "goal"):
                val = str(data.get(key, "")).strip()
                if val:
                    keywords.append(val.lower())
            for kw in data.get("keywords", []) or []:
                kw_s = str(kw).strip()
                if kw_s:
                    keywords.append(kw_s.lower())
        except (OSError, ValueError):
            pass

    if not keywords:
        try:
            from core.twin_interview import get_latest_profile

            profile = get_latest_profile(tenant_id)
            if profile:
                for key in ("role", "decision_style", "tools", "risk_posture", "work_ethics"):
                    val = str(profile.get(key, "")).strip()
                    if val:
                        keywords.append(val.lower())
        except Exception:  # pragma: no cover — best-effort
            pass

    return keywords


def inbox_score(tenant_id: str, text: str) -> dict[str, Any]:
    """Score an inbox message using Day-0 profile keywords only.

    Returns ``{"score": int, "matched": [...], "keywords": [...]}``.
    ``score`` is the count of profile keywords found (case-insensitive
    substring) in *text*.  No cloud model, no network.
    """
    keywords = _profile_keywords(tenant_id)
    lower_text = str(text).lower()
    matched: list[str] = []
    for kw in keywords:
        if kw and kw in lower_text:
            matched.append(kw)
    return {
        "score": len(matched),
        "matched": matched,
        "keywords": keywords,
    }


# ---------------------------------------------------------------------------#
# 5) Transcript gap guard
# ---------------------------------------------------------------------------#


def transcript_confidence(tenant_id: str, transcript_path: str) -> str:
    """Return the confidence level for a transcript-derived action.

    Returns ``"low"`` when the transcript file is missing or has
    empty/whitespace-only text (a gap).  Returns ``"high"`` otherwise.
    No network — pure file read.
    """
    path = Path(transcript_path)
    if not path.is_file():
        return "low"
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        return "low"
    return "high"


def flag_transcript_action(
    tenant_id: str,  # noqa: ARG001 — kept for API symmetry
    transcript_path: str,
    action: dict[str, Any],
) -> dict[str, Any]:
    """Attach a ``confidence`` key to *action* based on transcript gaps.

    Returns a copy of *action* with ``confidence`` set to ``"low"`` or
    ``"high"``.  Does not modify the original dict.
    """
    confidence = transcript_confidence(tenant_id, transcript_path)
    return {**action, "confidence": confidence}


# ---------------------------------------------------------------------------#
# 6) Delegate close guard
# ---------------------------------------------------------------------------#


def _delegate_pack_path(tenant_id: str) -> Path:
    """Return the path to ``delegate_pack.md`` for *tenant_id*."""
    return _work_products_dir(tenant_id) / "delegate_pack.md"


def delegate_close_link(
    tenant_id: str,
    decision_title: str,
    decision_id: str = "",
    pack_path: str | None = None,
) -> dict[str, Any]:
    """Write a local link back to the delegate pack when a delegate item is done.

    When a decision-record marks a delegate item as done, this writes a
    ``delegate_close.md`` file under ``work_products/{tenant_id}/`` with a
    link back to the pack file (if present) and the decision title/id.

    Returns ``{tenant_id, linked, path, decision_title, decision_id}``.
    No network.
    """
    if pack_path:
        pack = Path(pack_path)
    else:
        pack = _delegate_pack_path(tenant_id)
    linked = pack.is_file()

    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "delegate_close.md"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = [
        f"# Delegate Close — {tenant_id}",
        "",
        f"_Closed: {now}_",
        "",
        f"**Decision:** {decision_title}",
        "",
    ]
    if decision_id:
        lines.append(f"**Decision ID:** {decision_id}")
        lines.append("")
    if linked:
        lines.append(f"**Pack link:** [{pack.name}]({pack.as_posix()})")
    else:
        lines.append("_No delegate pack found — link not written._")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "linked": linked,
        "path": out_path.as_posix(),
        "decision_title": decision_title,
        "decision_id": decision_id,
    }
