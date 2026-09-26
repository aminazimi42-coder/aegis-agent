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

# T162 — PEM private-key begin markers.  ``-----BEGIN <TYPE> PRIVATE KEY-----``
# is the start of every PEM-encoded private key (RSA, EC, OPENSSH, …).
# T176 — redact the *entire* private-key block from begin to end marker so
# the key body is never persisted verbatim.
_PEM_BEGIN_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
)
_PEM_END_RE = re.compile(
    r"-----END [A-Z0-9 ]*PRIVATE KEY-----"
)

# T176 — SSH private-key blocks.  ``-----BEGIN OPENSSH PRIVATE KEY-----`` …
# ``-----END OPENSSH PRIVATE KEY-----`` is the standard OpenSSH private-key
# format.  The general PEM pattern above already covers the begin marker;
# this full-block pattern redacts the entire key body from begin to end.
_SSH_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN (?:OPENSSH|RSA|EC|DSA|PGP) PRIVATE KEY-----"
    r".*?-----END (?:OPENSSH|RSA|EC|DSA|PGP) PRIVATE KEY-----",
    re.DOTALL,
)

# T176 — webhook URL query secrets.  A webhook URL may carry a secret or
# token as a query parameter: ``https://hooks.example.com/…?secret=abc…``
# or ``…&token=xyz…``.  Redact the parameter value so the URL shape stays
# but the secret does not.
_WEBHOOK_SECRET_RE = re.compile(
    r"([?&](?:secret|token|key|webhook_secret)=[A-Za-z0-9_\-]{8,})",
    re.IGNORECASE,
)

# T190 — webhook secret prefix ``whsec_…``.  A webhook signing secret
# uses a distinctive prefix not covered by the query-param pattern above.
# Also redact common assignment shapes:
# ``whsec_secret=…``, ``webhook_secret=…``, ``WEBHOOK_SECRET=…``.
_WHSEC_PREFIX_RE = re.compile(
    r"whsec_[A-Za-z0-9]{16,}",
)
_WEBHOOK_ASSIGN_RE = re.compile(
    r"(?i)(?:whsec_secret|webhook_secret)"
    r"\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{8,}",
)

# T221 — Telegram bot token shape: ``<digits>:<token>`` (e.g.
# ``1234567890:AAHxxx...``).  Redact the token value after the colon.
_TG_BOT_TOKEN_RE = re.compile(
    r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b",
)

# T221 — bare ``token=…`` / ``chat_id=…`` assignment shapes (no query-prefix).
_TG_ASSIGN_RE = re.compile(
    r"(?i)(?:token|chat_id)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{8,}",
)

# T222 — SMTP password assignment shapes: ``password=…``,
# ``smtp_password=…``, ``AEGIS_SMTP_PASSWORD=…``.  Redact the value
# after the assignment operator.
_SMTP_PASSWORD_ASSIGN_RE = re.compile(
    r"(?i)(?:smtp_password|aegis_smtp_password|password)"
    r"\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{6,}",
)

_SECRET_SHAPES: tuple[re.Pattern[str], ...] = (
    _SK_RE,
    _GH_RE,
    _AWS_RE,
    _JWT_RE,
    _BEARER_RE,
    _SSH_KEY_BLOCK_RE,
    _PEM_BEGIN_RE,
    _PEM_END_RE,
    _WEBHOOK_SECRET_RE,
    _WHSEC_PREFIX_RE,
    _WEBHOOK_ASSIGN_RE,
    _TG_BOT_TOKEN_RE,
    _TG_ASSIGN_RE,
    _SMTP_PASSWORD_ASSIGN_RE,
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
