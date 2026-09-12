"""Local entitlement file reader (T131/T146).

Reads a single JSON file under ``AEGIS_DATA_DIR/entitlement.json`` to
determine the operator's tier.  The file carries:

* ``tenant_id``       — string identifying the tenant this file is bound to
* ``tier``            — ``"echo"`` or ``"professional"``
* ``expires_at``      — ISO-8601 UTC string or ``null``
* ``signature_sha256`` — SHA-256 hex digest of the canonical body
  (every field **except** ``signature_sha256``, serialised with
  ``sort_keys=True, separators=(",", ":")``).

When the file is **missing**, **unreadable**, **expired** (``expires_at``
is in the past), **signature-mismatched**, or **tenant-mismatched**,
:func:`load` returns ``tier="echo"`` with a typed ``reason``.  A missing
or malformed file never raises and never calls a network host.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from core.twin_local_view import data_root

ECHO_TIER: str = "echo"
PROFESSIONAL_TIER: str = "professional"
_VALID_TIERS: frozenset[str] = frozenset({ECHO_TIER, PROFESSIONAL_TIER})

# T154 — HMAC key for local-cli issuer.  When the entitlement carries
# ``issuer="local-cli"``, the ``signature_sha256`` field is an
# HMAC-SHA256 hex digest of the canonical body keyed with the issuer
# secret.  Legacy files (no ``issuer`` field) keep plain SHA-256 so
# prior tests and hand-issued files stay valid.
_ISSUER_KEY_ENV: str = "AEGIS_ENTITLEMENT_ISSUER_KEY"


def _entitlement_path() -> Path:
    """Return the path to the local entitlement file."""
    return data_root() / "entitlement.json"


def _canonical_body(data: dict[str, Any]) -> str:
    """Return the canonical JSON of *data* without ``signature_sha256``."""
    body = {k: v for k, v in data.items() if k != "signature_sha256"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _is_expired(expires_at: Any) -> bool:
    """Return True when *expires_at* is a past ISO-UTC string."""
    if expires_at is None:
        return False
    if not isinstance(expires_at, str):
        return True
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(expires_at)
    except (ValueError, TypeError):
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt < datetime.now(timezone.utc)


def _signature_valid(data: dict[str, Any]) -> bool:
    """Return True when ``signature_sha256`` matches the canonical body.

    When the file carries ``issuer="local-cli"``, the signature is an
    HMAC-SHA256 hex digest keyed with the issuer secret (read from
    ``AEGIS_ENTITLEMENT_ISSUER_KEY``).  Legacy files with no ``issuer``
    field use plain SHA-256 and stay valid without a key.
    """
    sig = data.get("signature_sha256")
    if not isinstance(sig, str) or not sig:
        return False
    body = _canonical_body(data)
    issuer = data.get("issuer")
    if isinstance(issuer, str) and issuer == "local-cli":
        key = os.getenv(_ISSUER_KEY_ENV, "")
        if not key:
            return False
        expected = hmac.new(
            key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(sig, expected)
    expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return sig == expected


def load(tenant_id: str | None = None) -> dict[str, Any]:
    """Load the local entitlement file and return a tier dict.

    When *tenant_id* is provided, the file's ``tenant_id`` field must
    match it; otherwise the tier degrades to ``echo`` with a typed
    ``reason``.  Returns ``{"tier": "echo", "reason": ...}`` when the
    file is missing, expired, malformed, signature-invalid, or
    tenant-mismatched.  Never calls a network host.
    """
    path = _entitlement_path()
    if not path.is_file():
        return {"tier": ECHO_TIER, "reason": "missing_file"}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError, TypeError):
        return {"tier": ECHO_TIER, "reason": "invalid_json"}
    if not isinstance(data, dict):
        return {"tier": ECHO_TIER, "reason": "invalid_json"}
    tier = data.get("tier")
    if not isinstance(tier, str) or tier not in _VALID_TIERS:
        return {"tier": ECHO_TIER, "reason": "invalid_tier"}
    if _is_expired(data.get("expires_at")):
        return {"tier": ECHO_TIER, "reason": "expired"}
    if not _signature_valid(data):
        return {"tier": ECHO_TIER, "reason": "signature_mismatch"}
    if tenant_id is not None:
        file_tenant = data.get("tenant_id")
        if not isinstance(file_tenant, str) or not file_tenant:
            return {"tier": ECHO_TIER, "reason": "tenant_id_missing"}
        if file_tenant != tenant_id:
            return {"tier": ECHO_TIER, "reason": "tenant_mismatch"}
    return {"tier": tier}


def current_tier(tenant_id: str | None = None) -> str:
    """Return the current entitlement tier as a string (``echo`` or ``professional``)."""
    return load(tenant_id=tenant_id).get("tier", ECHO_TIER)
