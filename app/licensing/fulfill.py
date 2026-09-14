"""Grant-gated local fulfillment helper outside execute (T173).

A *single* function — :func:`fulfill_local` — that writes a signed
``entitlement.json`` under ``AEGIS_DATA_DIR`` **only** when both of the
following are true:

1.  The ``grant`` argument is the exact string carried by the
    ``AEGIS_FULFILL_GRANT`` environment variable.
2.  The issuer key is present — either ``AEGIS_ENTITLEMENT_ISSUER_KEY``
    is set, or ``AEGIS_ENTITLEMENT_ISSUER_KEY_FILE`` points to a readable
    file containing the key.

When either condition fails, the function returns a typed refusal and
**writes nothing** to disk.

The function calls the *existing* local issuer writer
(``scripts.issue_entitlement``) — it does not fork a second issuer.
``scripts.issue_entitlement.issue`` builds and HMAC-SHA256-signs the
payload and writes ``entitlement.json`` under ``AEGIS_DATA_DIR``.

Design rules (enforced by tests):

* **Never imports stripe.**  No payment library is loaded.
* **Never opens a socket.**  No network call is made.
* **Never reads a card number.**  No payment fields are handled.
* **Propose, execute, approve, and complete_safe must not import this
  module.**  Fulfillment lives outside the twin core.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_GRANT_ENV: str = "AEGIS_FULFILL_GRANT"
_KEY_ENV: str = "AEGIS_ENTITLEMENT_ISSUER_KEY"
_KEY_FILE_ENV: str = "AEGIS_ENTITLEMENT_ISSUER_KEY_FILE"


def _issuer_key() -> str | None:
    """Return the issuer secret from the environment or key file.

    Returns ``None`` when neither source provides a key.
    """
    val = os.getenv(_KEY_ENV, "").strip()
    if val:
        return val
    key_file = os.getenv(_KEY_FILE_ENV, "").strip()
    if key_file:
        p = Path(key_file)
        if p.is_file():
            raw = p.read_text(encoding="utf-8")
            return raw.strip()
    return None


def fulfill_local(
    tenant_id: str,
    tier: str,
    days: int,
    grant: str,
) -> dict[str, Any]:
    """Write a signed ``entitlement.json`` only when the grant and key match.

    *grant* must equal the exact string in ``AEGIS_FULFILL_GRANT``.
    The issuer key must be present (``AEGIS_ENTITLEMENT_ISSUER_KEY`` env
    or ``AEGIS_ENTITLEMENT_ISSUER_KEY_FILE`` file path).

    On success, returns a dict with ``fulfill_state: "fulfilled"`` and the
    signed payload.  On refusal, returns a dict with
    ``fulfill_state: "refused"`` and a typed ``reason`` — and **writes
    nothing** to disk.

    Never imports stripe.  Never opens a socket.  Never reads a card
    number.
    """
    expected = os.getenv(_GRANT_ENV, "").strip()
    if not expected or not isinstance(grant, str) or grant != expected:
        return {"fulfill_state": "refused", "reason": "wrong_grant"}

    key = _issuer_key()
    if not key:
        return {"fulfill_state": "refused", "reason": "missing_key"}

    # Call the existing local issuer — do not fork a second issuer.
    from scripts.issue_entitlement import issue

    payload = issue(tenant_id, tier, days, key, source="external_checkout")
    return {"fulfill_state": "fulfilled", "payload": payload}
