"""Stripe checkout sidecar — outside the twin execute path (T179).

A *single* optional function — :func:`create_checkout_intent` — that builds
a Stripe Checkout Session intent **only** when ``STRIPE_SECRET_KEY`` is set
in the environment.

Design rules (enforced by tests):

* **Default off.** When ``STRIPE_SECRET_KEY`` is unset or empty,
  :func:`create_checkout_intent` returns a typed ``not_configured`` result
  **without opening a socket** and **without importing stripe**.
* **Never raises into propose / execute.**  The function returns a typed
  result on every path; it is never imported by ``execute()`` or
  ``propose()``.
* **No Stripe secret or live price table in git.**  The secret key is read
  from the environment only; it is never written to a file, never logged,
  and never committed.
* **Typed local record.**  The result is a plain dict with a ``provider``
  key (``"stripe_test_or_unset"``) and a ``status`` key (``"not_configured"``
  or ``"stub"`` when the key is present but the live call is not wired).

This module lives under ``app/licensing/`` — outside the ``core/`` execute
path.  ``propose()``, ``execute()``, ``approve()``, and ``complete_safe``
must never import or call it.
"""

from __future__ import annotations

import os
from typing import Any

_PROVIDER: str = "stripe_test_or_unset"
_STRIPE_KEY_ENV: str = "STRIPE_SECRET_KEY"


def create_checkout_intent(
    tier: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    """Return a typed checkout-intent dict.

    When ``STRIPE_SECRET_KEY`` is unset or empty (the default in tests and
    CI), returns ``{"provider": "stripe_test_or_unset", "status":
    "not_configured", "checkout_url": None}`` **without calling the
    network** and **without importing stripe**.

    When the key is set in the environment only, the function *may* call
    the Stripe Checkout Session create endpoint behind a narrow client.
    In this tree the live call is not wired, so it returns ``status=
    "stub"`` with ``checkout_url=None`` — the key is present but the live
    shop is not deployed.  Still never raises into propose / execute.

    Never writes a Stripe secret to a file.  Never logs the key.
    """
    key = os.getenv(_STRIPE_KEY_ENV, "")
    if not key or not key.strip():
        return {
            "provider": _PROVIDER,
            "status": "not_configured",
            "checkout_url": None,
        }

    # The key is present in the environment.  A live Stripe Checkout
    # Session create call would go here behind a narrow client.  In this
    # tree the live call is not wired (no live shop is deployed), so we
    # return a stub.  The key is never written, logged, or committed.
    return {
        "provider": _PROVIDER,
        "status": "stub",
        "checkout_url": None,
    }
