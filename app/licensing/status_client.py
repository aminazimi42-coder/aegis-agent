"""Optional labeled HTTP license-status client (T151).

A *single* optional function — :func:`check_remote_status` — that issues a
labeled ``GET`` request to an operator-configured license-status host.

Design rules (enforced by tests):

* **Default off.** When ``AEGIS_LICENSE_STATUS_URL`` is unset or empty,
  :func:`check_remote_status` returns a typed ``local_only`` result
  **without opening a socket.**
* **GET-only.** The function issues a single ``GET`` with a ≤ 2-second
  timeout, no request body, no cookies, and no ``Authorization`` header
  unless ``AEGIS_LICENSE_BEARER`` is set.
* **Parse-strict.** Only ``{tier, expires_at, status}`` are read; unknown
  fields are ignored.
* **Never raises.** On timeout, DNS failure, TLS failure, or non-200
  status, a typed ``remote_unreachable`` result is returned.
* **Never sends the local entitlement file or profile fields.**
* **Never POSTs.**

The result is a plain dict with a ``license_check`` key — one of
``"local_only"``, ``"remote_ok"``, ``"remote_unreachable"``, or
``"echo_limited"``.

This module is imported **only** by the operator-page / status-payload
read path.  The ``propose`` and ``execute`` paths must not import or call
it.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_TIMEOUT_SECONDS: float = 2.0
_VALID_REMOTE_TIERS: frozenset[str] = frozenset({"echo", "professional"})


def check_remote_status() -> dict[str, Any]:
    """Return a typed license-status dict.

    When ``AEGIS_LICENSE_STATUS_URL`` is unset or empty, returns
    ``{"license_check": "local_only"}`` without opening a socket.

    When the URL is set, issues a single ``GET`` (≤ 2 s timeout, no body,
    no cookies, optional bearer).  On success parses ``{tier,
    expires_at, status}`` and returns ``{"license_check": "remote_ok",
    ...}``.  On any failure returns
    ``{"license_check": "remote_unreachable"}``.

    Never raises.
    """
    url = os.getenv("AEGIS_LICENSE_STATUS_URL", "")
    if not url or not url.strip():
        return {"license_check": "local_only"}

    url = url.strip()

    # Build a GET request — no body, no cookies.
    req = Request(url, method="GET")
    req.add_header("Accept", "application/json")

    bearer = os.getenv("AEGIS_LICENSE_BEARER", "")
    if bearer and bearer.strip():
        req.add_header("Authorization", "Bearer " + bearer.strip())

    try:
        with urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:  # noqa: S310
            status_code = resp.status
            if status_code != 200:
                return {"license_check": "remote_unreachable"}
            raw = resp.read()
    except (URLError, HTTPError, OSError, TimeoutError, ConnectionError, json.JSONDecodeError):
        return {"license_check": "remote_unreachable"}
    except Exception:
        # Catch-all: never raise into the caller.
        return {"license_check": "remote_unreachable"}

    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {"license_check": "remote_unreachable"}

    if not isinstance(data, dict):
        return {"license_check": "remote_unreachable"}

    # Parse only {tier, expires_at, status}; ignore unknown fields.
    tier = data.get("tier")
    if isinstance(tier, str) and tier not in _VALID_REMOTE_TIERS:
        tier = None

    result: dict[str, Any] = {"license_check": "remote_ok"}
    if isinstance(tier, str):
        result["tier"] = tier
    expires_at = data.get("expires_at")
    if isinstance(expires_at, str) or expires_at is None:
        result["expires_at"] = expires_at
    status = data.get("status")
    if isinstance(status, str):
        result["status"] = status
    return result
