"""T92 — Untrusted external-text ingest with provenance and injection gate.

External text (``.eml`` files, pasted mail, raw external snippets) enters the
twin through :func:`ingest_untrusted`.  Every piece of external text is marked
``provenance="untrusted"`` and is scanned for execute/approve instruction
patterns before it can become a twin event.  Injection-shaped content is
rejected (``ValueError("injection-shaped: ..."``) and never reaches
:func:`core.twin_events.ingest_event`.

A trusted local ``profile.json`` is **not** untrusted; pass it through the
trusted path (:mod:`core.twin_interview`) instead.

No network — no ``urllib``, ``requests``, ``socket``, or ``http.client``
imports are used.
"""

from __future__ import annotations

import re
from typing import Any

from core.twin_events import ingest_event

# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #

TRUSTED = "trusted"
UNTRUSTED = "untrusted"

# --------------------------------------------------------------------------- #
# Injection detection — execute / approve instruction patterns
# --------------------------------------------------------------------------- #

# Patterns that indicate the external text is trying to become an executable
# payload rather than a passive observation.  We match case-insensitively on
# whole-line instructions so benign mentions ("the approve button") pass.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "execute <action>", "execute action <id>"
    re.compile(r"(?im)^\s*execute\b", re.IGNORECASE),
    # "approve <action>", "approve action <id>"
    re.compile(r"(?im)^\s*approve\b", re.IGNORECASE),
    # "run <cmd>", "run command"
    re.compile(r"(?im)^\s*run\b", re.IGNORECASE),
    # "system: <instruction>", "system prompt:"
    re.compile(r"(?im)^\s*system\s*[:=]\s*\S", re.IGNORECASE),
    # "ignore previous instructions"
    re.compile(r"(?im)ignore\s+(previous|prior|all)\s+instructions", re.IGNORECASE),
    # "disregard the above"
    re.compile(r"(?im)disregard\s+(the\s+)?(above|prior|previous)", re.IGNORECASE),
    # "you must approve", "you must execute"
    re.compile(r"(?im)^\s*you\s+must\s+(approve|execute|run)\b", re.IGNORECASE),
    # "act as", "pretend to be" — role hijack
    re.compile(r"(?im)^\s*(act\s+as|pretend\s+to\s+be)\b", re.IGNORECASE),
    # "<execute>...</execute>" style tags
    re.compile(r"(?im)<\s*(execute|approve|run)\b[^>]*>", re.IGNORECASE),
)


def _contains_injection(text: str) -> str | None:
    """Return the matched pattern description if *text* is injection-shaped."""
    if not text:
        return None
    for pat in _INJECTION_PATTERNS:
        m = pat.search(text)
        if m is not None:
            return m.group(0).strip()
    return None


# Map external origins to valid twin-event sources (twin_events._VALID_SOURCES).
_EVENT_SOURCE: dict[str, str] = {
    "email": "email",
    "external": "manual",
    "paste": "manual",
    "raw": "manual",
}


def is_untrusted(source: str) -> bool:
    """Return ``True`` when *source* is an external/untrusted origin."""
    return source in _EVENT_SOURCE


def ingest_untrusted(
    tenant_id: str,
    source: str,
    kind: str,
    text: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ingest external text marked ``provenance="untrusted"``.

    * Parses and marks the source as untrusted.
    * Rejects injection-shaped text (execute/approve instruction patterns)
      before any twin event is created — raises ``ValueError("injection-shaped:
      ...")`` and returns nothing.
    * On clean text, ingests a twin event whose payload carries
      ``provenance="untrusted"`` and the (length-limited) text body.

    Returns the ingested event dict with ``provenance`` set to ``"untrusted"``.
    """
    if not is_untrusted(source):
        raise ValueError(f"not an untrusted source: {source!r}")

    # Scan the raw external text for instruction-injection patterns.
    hit = _contains_injection(text)
    if hit is not None:
        raise ValueError(f"injection-shaped: {hit[:80]}")

    body = (text or "")[:400]
    pl: dict[str, Any] = {
        "provenance": UNTRUSTED,
        "text": body,
    }
    if payload:
        pl.update(payload)

    event = ingest_event(
        tenant_id=tenant_id,
        source=_EVENT_SOURCE[source],
        kind=kind,
        payload=pl,
    )
    return {**event, "provenance": UNTRUSTED}
