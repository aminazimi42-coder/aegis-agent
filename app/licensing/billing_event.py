"""Stripe checkout-event handler — outside the twin execute path (T188).

A *single* function — :func:`handle_checkout_event` — that processes a
Stripe checkout webhook payload and, for a valid ``checkout.session.completed``
event with a local tenant and an allowed tier, calls the *existing* local
issuer (``scripts.issue_entitlement.issue``) to write ``entitlement.json``
under ``AEGIS_DATA_DIR``.

Design rules (enforced by tests):

* **Default off.** When ``STRIPE_WEBHOOK_SECRET`` is unset or empty,
  :func:`handle_checkout_event` returns ``status=not_configured``
  **without writing to disk** and **without calling the network**.
* **Signature check.** When the secret is set in the environment only,
  a signature header is required.  An invalid or missing signature
  returns ``status=rejected`` and **writes nothing**.
* **Completed event with valid tenant + allowed tier.**  Calls the
  existing local issuer to write ``entitlement.json`` under
  ``AEGIS_DATA_DIR``.  The tier is taken from the event payload only —
  never from an unauthenticated query string.
* **Unknown event type.** Returns ``status=ignored`` and writes nothing.
* **Never imported from execute, propose, or complete_safe.**  This
  handler lives outside the twin core.
* **Never imports stripe.**  No payment library is loaded.

The returned typed record is a plain dict with a ``status`` key
(``not_configured`` | ``ignored`` | ``issued`` | ``rejected``).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

_WEBHOOK_SECRET_ENV: str = "STRIPE_WEBHOOK_SECRET"
_KEY_ENV: str = "AEGIS_ENTITLEMENT_ISSUER_KEY"
_KEY_FILE_ENV: str = "AEGIS_ENTITLEMENT_ISSUER_KEY_FILE"
_ALLOWED_TIERS: tuple[str, ...] = ("echo", "professional")


def _issuer_key() -> str | None:
    """Return the issuer secret from the environment or key file.

    Returns ``None`` when neither source provides a key.
    """
    val = os.getenv(_KEY_ENV, "").strip()
    if val:
        return val
    key_file = os.getenv(_KEY_FILE_ENV, "").strip()
    if key_file:
        from pathlib import Path

        p = Path(key_file)
        if p.is_file():
            raw = p.read_text(encoding="utf-8")
            return raw.strip()
    return None


def _verify_signature(payload: bytes, signature_header: str | None, secret: str) -> bool:
    """Return True when *signature_header* is a valid Stripe webhook signature."""
    if not signature_header:
        return False
    # Stripe sends ``t=<timestamp>,v1=<signature>`` — split and verify.
    parts: dict[str, str] = {}
    for chunk in signature_header.split(","):
        chunk = chunk.strip()
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            parts[k.strip()] = v.strip()
    timestamp = parts.get("t", "")
    sig = parts.get("v1", "")
    if not timestamp or not sig:
        return False
    signed_payload = f"{timestamp}.{payload.decode('utf-8', errors='replace')}"
    expected = hmac.new(
        secret.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


def handle_checkout_event(
    payload: bytes | str,
    signature_header: str | None = None,
) -> dict[str, Any]:
    """Handle a Stripe checkout-event payload and return a typed record.

    *payload* is the raw webhook body (bytes or str).
    *signature_header* is the ``Stripe-Signature`` header value or None.

    Returns a dict with a ``status`` key:

    - ``not_configured`` — ``STRIPE_WEBHOOK_SECRET`` is unset; no disk write,
      no network.
    - ``rejected`` — the secret is set but the signature is missing or
      invalid; no disk write.
    - ``ignored`` — the event type is unknown; no disk write.
    - ``issued`` — a completed event with a valid local tenant and an
      allowed tier; the local issuer wrote ``entitlement.json`` under
      ``AEGIS_DATA_DIR``.

    Never imports stripe.  Never raises into execute or propose.
    """
    import json

    secret = os.getenv(_WEBHOOK_SECRET_ENV, "")
    if not secret or not secret.strip():
        return {"status": "not_configured"}

    # Secret is present — require a valid signature.
    if isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = payload

    if not _verify_signature(raw, signature_header, secret.strip()):
        return {"status": "rejected"}

    # Parse the event JSON.
    try:
        event = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"status": "ignored"}

    event_type = event.get("type", "")
    if event_type != "checkout.session.completed":
        return {"status": "ignored"}

    # Extract tenant and tier from the event payload only — never from a
    # query string.
    data = event.get("data", {}).get("object", {})
    tenant_id = data.get("client_reference_id") or data.get("metadata", {}).get(
        "tenant_id"
    )
    tier = data.get("metadata", {}).get("tier", "echo")

    if not tenant_id or not isinstance(tenant_id, str):
        return {"status": "ignored"}
    if tier not in _ALLOWED_TIERS:
        return {"status": "ignored"}

    # Call the existing local issuer — do not fork a second issuer.
    # The issuer key comes from the environment (AEGIS_ENTITLEMENT_ISSUER_KEY
    # or AEGIS_ENTITLEMENT_ISSUER_KEY_FILE), not from the webhook secret.
    from scripts.issue_entitlement import issue

    key = _issuer_key()
    if not key:
        return {"status": "rejected"}
    issue(tenant_id, tier, 30, key, source="external_checkout")
    return {"status": "issued", "tenant_id": tenant_id, "tier": tier}
