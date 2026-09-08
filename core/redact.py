"""T124 — Secret-shape redaction and untrusted-source prefilter.

Local, regex-based redaction of secret-shaped substrings in proposed card
text, audit JSONL, and untrusted pasted text.  No outbound scanner, no
remote DLP API.

Patterns redacted (replaced with ``[REDACTED]``):

* ``sk-…`` / ``sk_…`` / ``sk_live_…`` — OpenAI-style / payment-processor API keys
* ``gh[pous]_…`` — GitHub personal-access / OAuth / server / app tokens
* ``AKIA…`` — 20-char AWS access-key IDs
* ``Bearer <token>`` — bearer tokens (the ``Bearer`` prefix is kept, the
  trailing token value is redacted)
* ``eyJ….….`` — JWT-shaped tokens

The :func:`redact` function operates on a single string; the
:func:`redact_payload` function walks dict / list / str values so a full
payload (or audit ``extra`` dict) can be redacted in one call.
"""

from __future__ import annotations

import re
from typing import Any

# --------------------------------------------------------------------------- #
# Secret-shape patterns (shape-only, no env-var lookup, no network)
# --------------------------------------------------------------------------- #

# ``sk``-prefixed API keys: sk-…, sk_…, sk_live_…, ``Bearer sk-…``
_SK_RE = re.compile(
    r"(?:Bearer\s+)?sk[-_:][A-Za-z0-9_-]{8,}",
    re.IGNORECASE,
)

# GitHub tokens: ghp_…, gho_…, ghu_…, ghs_…  (36 hex chars, but match shape)
_GH_RE = re.compile(
    r"gh[pous]_[A-Za-z0-9]{16,}",
)

# AWS access-key IDs: 20 chars of [A-Z0-9], start with AKIA.
_AWS_RE = re.compile(
    r"AKIA[0-9A-Z]{16}",
)

# JWT tokens: three base64url segments, first starts with eyJ.
_JWT_RE = re.compile(
    r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
)

# ``Bearer <token>`` — keep the ``Bearer`` prefix, redact the value.  This
# is applied *after* the ``sk`` pattern so that ``Bearer sk-…`` is handled by
# the more specific pattern first; this catches ``Bearer eyJ…`` and other
# bare bearer values.
_BEARER_RE = re.compile(
    r"(?i)Bearer\s+[A-Za-z0-9_\-\.]{8,}",
)

_SECRET_SHAPES: tuple[re.Pattern[str], ...] = (
    _SK_RE,
    _GH_RE,
    _AWS_RE,
    _JWT_RE,
    _BEARER_RE,
)

_REPLACEMENT = "[REDACTED]"


def redact(text: str) -> str:
    """Replace every secret-shaped substring in *text* with ``[REDACTED]``.

    No network, no env-var lookup — purely shape-based regex matching.
    Returns the original string unchanged when *text* is falsy.
    """
    if not text:
        return text
    for pattern in _SECRET_SHAPES:
        text = pattern.sub(_REPLACEMENT, text)
    return text


def redact_payload(value: Any) -> Any:
    """Recursively redact secret-shaped strings inside *value*.

    Walks dicts, lists, and strings; other types pass through unchanged.
    """
    if isinstance(value, dict):
        return {key: redact_payload(val) for key, val in value.items()}
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        return redact(value)
    return value
