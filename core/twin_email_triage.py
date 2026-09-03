"""Local email triage drafts for the cognitive twin.

``triage(tenant_id, mail_dir)`` reads a folder of ``.eml`` files, parses each
with ``email.message_from_binary_file``, ingests a deduplicated ``email`` /
``message`` twin event for every new ``(from, subject)`` pair, and writes a
local ``email_triage.md`` with one section per message plus a deterministic
2-sentence draft reply.  No network send, no IMAP/SMTP, no LLM.
"""

from __future__ import annotations

import email
import os
from pathlib import Path
from typing import Any

from core.twin_events import ingest_event, list_events
from core.twin_evolution import evolve
from core.twin_interview import get_latest_profile

_MAX_BODY = 400


def _triage_path(tenant_id: str) -> Path:
    """Return the path to ``email_triage.md`` for *tenant_id*."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id / "email_triage.md"


def _parse_eml(eml_path: Path) -> dict[str, str] | None:
    """Parse a single ``.eml`` file; return ``{from, subject, body}`` or ``None``."""
    try:
        msg = email.message_from_binary_file(open(eml_path, "rb"))
    except Exception:
        return None

    sender = msg.get("From", "")
    subject = msg.get("Subject", "")

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    body = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            body = payload.decode("utf-8", errors="replace")

    body = body[:_MAX_BODY]
    return {"from": sender, "subject": subject, "body": body}


def _draft_reply(sender: str, subject: str) -> str:
    """Return a deterministic 2-sentence draft reply (not a live LLM)."""
    return (
        f"Thank you for your message about {subject!s}. "
        f"I will review it and follow up with you, {sender!s}, shortly."
    )


def _render_markdown(
    tenant_id: str,
    messages: list[dict[str, str]],
) -> str:
    """Render the triage markdown with one section per message + draft reply."""
    lines: list[str] = [
        f"# Email Triage — {tenant_id}",
        "",
    ]
    if not messages:
        lines.append("_No messages to triage._")
        lines.append("")
        return "\n".join(lines)

    for i, msg in enumerate(messages, start=1):
        lines.append(f"## {i}. {msg['subject']}")
        lines.append("")
        lines.append(f"**From:** {msg['from']}")
        lines.append("")
        if msg.get("body"):
            lines.append(f"**Body:** {msg['body']}")
            lines.append("")
        lines.append("**Draft reply:**")
        lines.append("")
        lines.append(f"> {_draft_reply(msg['from'], msg['subject'])}")
        lines.append("")

    return "\n".join(lines)


def triage(tenant_id: str, mail_dir: str) -> dict[str, Any]:
    """Triage a folder of ``.eml`` files for *tenant_id*.

    Requires a consented twin profile (raises ``ValueError("no consented
    profile")`` otherwise) and that ``mail_dir`` is an existing directory
    (raises ``ValueError("mail dir not found")`` otherwise).

    Parses each ``*.eml`` with ``email.message_from_binary_file``, deduplicates
    by ``(from, subject)``, ingests a deduplicated ``email`` / ``message`` twin
    event for each new pair, feeds it through ``evolve``, and writes
    ``email_triage.md`` under ``work_products/{tenant_id}/``.

    Returns ``{"tenant_id": ..., "ingested": N, "path": ...}``.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    if not Path(mail_dir).is_dir():
        raise ValueError("mail dir not found")

    # Collect existing (from, subject) pairs for dedup.
    existing: set[tuple[str, str]] = set()
    for ev in list_events(tenant_id, limit=500):
        if ev.get("source") == "email" and ev.get("kind") == "message":
            payload = ev.get("payload") or {}
            f = payload.get("from")
            s = payload.get("subject")
            if f is not None and s is not None:
                existing.add((str(f), str(s)))

    eml_files = sorted(Path(mail_dir).glob("*.eml"))
    messages: list[dict[str, str]] = []
    ingested = 0

    for eml_path in eml_files:
        parsed = _parse_eml(eml_path)
        if parsed is None:
            continue
        key = (parsed["from"], parsed["subject"])
        if key in existing:
            continue
        existing.add(key)
        messages.append(parsed)

        event = ingest_event(
            tenant_id=tenant_id,
            source="email",
            kind="message",
            payload={"from": parsed["from"], "subject": parsed["subject"]},
        )
        evolve(tenant_id, event)
        ingested += 1

    content = _render_markdown(tenant_id, messages)

    out_path = _triage_path(tenant_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "ingested": ingested,
        "path": out_path.as_posix(),
    }
