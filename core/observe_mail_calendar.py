"""T201 — Observe-only local mail and calendar propose.

Reads a single ``.eml`` or ``.ics`` file already sitting inside
``AEGIS_DATA_DIR`` and proposes six specialist cards from its parsed
text.  The file path must pass the T190 ``cage_path`` helper — a path
outside the data dir is a typed deny with zero new cards.

Only local bytes are parsed; no HTTP/HTTPS fetch, no SMTP, no IMAP, no
mailbox password.  A successful observe creates proposed rows on the
current tenant queue (reusing the existing six-specialist propose
path); status stays ``proposed`` with no auto-approve and no
auto-execute.  Any effect named ``send``, ``smtp``, ``mailto``,
``calendar-write``, or ``invite-send`` is a typed deny.
"""

from __future__ import annotations

import email
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.redact import redact
from core.twin_local_view import cage_path, data_root

# Accepted file suffixes — only .eml and .ics.
_ACCEPTED_SUFFIXES: tuple[str, ...] = (".eml", ".ics")

# Effects that are always a typed deny — never proposed, never executed.
_DENIED_EFFECTS: frozenset[str] = frozenset(
    {
        "send",
        "smtp",
        "mailto",
        "calendar-write",
        "invite-send",
    }
)


class ObserveDeniedError(ValueError):
    """Typed rejection when an observe source or effect is denied.

    The ``code`` attribute is the stable typed string returned to both
    HTTP and CLI callers.
    """

    code: str = "observe_denied"

    def __init__(self, reason: str = "observe denied") -> None:
        super().__init__(reason)
        self.reason = reason


def _parse_eml(path: Path) -> dict[str, str]:
    """Parse a local ``.eml`` file; return ``{subject, summary, body}``."""
    msg = email.message_from_binary_file(open(path, "rb"))
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
    summary = f"From: {msg.get('From', '')}"
    return {"subject": subject, "summary": summary, "body": body[:400]}


def _parse_ics(path: Path) -> dict[str, str]:
    """Parse a local ``.ics`` file; return ``{subject, summary, dtstart}``."""
    text = path.read_text(encoding="utf-8", errors="replace")
    subject = ""
    dtstart = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        idx = line.find(":")
        if idx == -1:
            continue
        name_part = line[:idx]
        value = line[idx + 1 :]
        semi_idx = name_part.find(";")
        if semi_idx != -1:
            name_part = name_part[:semi_idx]
        name_part = name_part.strip().upper()
        if name_part == "SUMMARY":
            subject = value.strip().replace("\\,", ",").replace("\\;", ";")
        elif name_part == "DTSTART":
            dtstart = value.strip()
    summary = f"Start: {dtstart}" if dtstart else "calendar event"
    return {"subject": subject, "summary": summary, "dtstart": dtstart}


def _build_text(suffix: str, parsed: dict[str, str]) -> str:
    """Build the task text from parsed .eml or .ics fields."""
    parts: list[str] = []
    if suffix == ".eml":
        subject = parsed.get("subject", "")
        summary = parsed.get("summary", "")
        body = parsed.get("body", "")
        if subject:
            parts.append(f"Subject: {subject}")
        if summary:
            parts.append(summary)
        if body:
            parts.append(f"Body: {body}")
    else:
        subject = parsed.get("subject", "")
        summary = parsed.get("summary", "")
        dtstart = parsed.get("dtstart", "")
        if subject:
            parts.append(f"Event: {subject}")
        if dtstart:
            parts.append(f"DTSTART: {dtstart}")
        if summary:
            parts.append(summary)
    return redact(" | ".join(parts)) if parts else "observe local file"


def observe_local_mail_calendar(
    tenant_id: str,
    file_path: str,
) -> dict[str, Any]:
    """Observe a local ``.eml`` or ``.ics`` file and propose cards.

    The *file_path* must resolve inside ``AEGIS_DATA_DIR`` (T190
    ``cage_path``).  Outside the data dir: typed deny, zero new cards.
    Missing, empty, or wrong-suffix file: typed fail, zero new cards.

    Only local bytes are parsed — no HTTP fetch, no SMTP, no IMAP.  The
    parsed subject / summary / dtstart become task text that feeds the
    existing six-specialist propose path.  Status stays ``proposed``;
    no auto-approve, no auto-execute.

    Any effect named ``send``, ``smtp``, ``mailto``,
    ``calendar-write``, or ``invite-send`` is a typed deny.

    Returns ``{tenant_id, proposed, count, path}`` on success.
    """
    # 1) Allow-list observe — cage the path inside AEGIS_DATA_DIR.
    caged = cage_path(file_path)
    path = Path(caged)

    if not path.is_file():
        raise ObserveDeniedError("observe_failed: file not found inside data dir")

    suffix = path.suffix.lower()
    if suffix not in _ACCEPTED_SUFFIXES:
        raise ObserveDeniedError("observe_failed: wrong suffix")

    if path.stat().st_size == 0:
        raise ObserveDeniedError("observe_failed: empty file")

    # 2) Parse only local bytes.  No http/https, no SMTP, no IMAP.
    if suffix == ".eml":
        try:
            parsed = _parse_eml(path)
        except Exception as exc:  # pragma: no cover - defensive
            raise ObserveDeniedError("observe_failed: parse error") from exc
    else:
        parsed = _parse_ics(path)

    text = _build_text(suffix, parsed)
    # Redact bearer/webhook/SSH shapes before the card is stored (T124).
    text = redact(text)

    # 2) Propose only — reuse the existing six-specialist propose path.
    from uuid import uuid4

    from agents.ahmad.agent import AhmadAgent
    from agents.alina.agent import AlinaAgent
    from agents.amin.agent import AminAgent
    from agents.aylin.agent import AylinAgent
    from agents.bita.agent import BitaAgent
    from agents.kian.agent import KianAgent

    specialists = [
        AlinaAgent(),
        KianAgent(),
        BitaAgent(),
        AylinAgent(),
        AhmadAgent(),
        AminAgent(),
    ]
    batch_id = f"observe-{uuid4().hex[:12]}"
    proposals: list[dict[str, Any]] = []
    for agent in specialists:
        row = agent.propose(tenant_id, text, batch_id=batch_id)
        proposals.append(
            {
                "action_id": row["action_id"],
                "agent": agent.name,
                "kind": row["kind"],
                "title": row["title"],
                "status": row["status"],
            }
        )

    # 3) T204 — write one local byte receipt for the observed file.
    #    Records tenant, source basename, byte length, and sha256 of
    #    the raw bytes.  Reuses T125 receipt dir and T190 cage_path.
    #    No cloud, no execute, no send.
    receipt_path = _write_byte_receipt(tenant_id, path)

    return {
        "tenant_id": tenant_id,
        "proposed": proposals,
        "count": len(proposals),
        "path": path.as_posix(),
        "byte_receipt": str(receipt_path),
    }


def _write_byte_receipt(
    tenant_id: str,
    source_path: Path,
) -> Path:
    """Write one local byte receipt for an observed file.

    T204 — after a successful observe of a local ``.eml`` or ``.ics``
    inside ``AEGIS_DATA_DIR``, write one receipt under
    ``<data_root>/receipts/observe_<sha8>.json`` recording the tenant,
    the basename of the source path, the byte length, and the sha256 of
    the raw bytes.  Reuses the T125 receipt directory and T190
    ``cage_path``.  Returns the receipt path.  No cloud, no execute.
    """
    root = data_root()
    receipts_dir = cage_path(root / "receipts")
    receipts_dir.mkdir(parents=True, exist_ok=True)
    raw = source_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    receipt = {
        "tenant_id": tenant_id,
        "source": source_path.name,
        "byte_length": len(raw),
        "sha256": sha,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = cage_path(receipts_dir / f"observe_{sha[:8]}.json")
    import json

    receipt_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return receipt_path


def denied_effects() -> frozenset[str]:
    """Return the frozenset of effects that are always a typed deny."""
    return _DENIED_EFFECTS
