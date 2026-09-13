"""Optional external checkout URL helper (T170).

A *single* optional function — :func:`checkout_url` — that reads an
operator-configured external checkout URL from the ``AEGIS_CHECKOUT_URL``
environment variable.

Design rules (enforced by tests):

* **Default off.** When ``AEGIS_CHECKOUT_URL`` is unset or empty,
  :func:`checkout_url` returns a typed ``checkout_unset`` result
  **without opening a socket** and **without importing stripe**.
* **URL-only.** When the URL is set, the function returns that URL
  string only.  It does not append profile fields, does not append
  ``entitlement.json``, and does not send a POST.
* **Never persists a card number.** The function never reads or logs a
  card number, secret key, or payment date.
* **No live shop.** No live Stripe shop is deployed in this slice.

The result is a plain dict with a ``checkout_state`` key — one of
``"checkout_unset"`` or ``"url_ready"`` — and, when the URL is set, a
``"checkout_url"`` key carrying the URL string.

This module is imported **only** by the operator-page / status-payload
read path.  The ``propose`` and ``execute`` paths must not import or
call it.
"""

from __future__ import annotations

import os
from typing import Any


def checkout_url() -> dict[str, Any]:
    """Return a typed checkout-URL dict.

    When ``AEGIS_CHECKOUT_URL`` is unset or empty, returns
    ``{"checkout_state": "checkout_unset"}`` without opening a socket
    and without importing stripe.

    When the URL is set, returns
    ``{"checkout_state": "url_ready", "checkout_url": <url>}`` — the
    URL string only.  Does not append profile fields, does not append
    ``entitlement.json``, and does not send a POST.

    Never persists a card number.  Never logs a secret key.
    """
    url = os.getenv("AEGIS_CHECKOUT_URL", "")
    if not url or not url.strip():
        return {"checkout_state": "checkout_unset"}
    return {"checkout_state": "url_ready", "checkout_url": url.strip()}
