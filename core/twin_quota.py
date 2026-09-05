"""Local cloud-quota ledger for each tenant (T80).

The quota row tracks how many *remaining* units a tenant has for the current
billing ``period`` and when that period ends.  The ledger is persisted as a
single JSON file under ``{AEGIS_DATA_DIR}/quota/{tenant_id}.json`` — it lives
**outside** the ``twin_actions`` table and never carries payment, card, or
customer identifiers.

The public surface is intentionally tiny:

* :func:`get_quota` — read the current quota dict (``remaining``, ``period_end``).
  Returns ``remaining=0`` with an empty ``period_end`` when no row exists yet.
* :func:`set_quota` — overwrite the quota row for a tenant and return the
  stored dict.

No live network is used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.twin_local_view import data_root


def _quota_dir() -> Path:
    """Return the directory where per-tenant quota files live."""
    path = data_root() / "quota"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _quota_path(tenant_id: str) -> Path:
    """Return the JSON file path for *tenant_id*'s quota row."""
    safe = "".join(
        ch if ch.isalnum() or ch in ("-", "_", ".") else "_"
        for ch in tenant_id
    ) or "unknown"
    return _quota_dir() / f"{safe}.json"


def get_quota(tenant_id: str) -> dict[str, Any]:
    """Return the quota row for *tenant_id*.

    The returned dict always has the keys ``remaining`` (int) and
    ``period_end`` (str).  When no row has been written yet the default
    ``remaining`` is ``0`` and ``period_end`` is an empty string.
    """
    path = _quota_path(tenant_id)
    if path.is_file():
        row = json.loads(path.read_text(encoding="utf-8"))
        return {
            "remaining": int(row.get("remaining", 0)),
            "period_end": str(row.get("period_end", "")),
        }
    return {"remaining": 0, "period_end": ""}


def set_quota(
    tenant_id: str,
    remaining: int,
    period_end: str,
) -> dict[str, Any]:
    """Persist the quota row for *tenant_id* and return it.

    ``remaining`` is stored as an int; ``period_end`` is stored as-is (a
    date or ISO-8601 string).  No card, payment, or customer identifiers are
    accepted or stored.
    """
    row = {
        "remaining": int(remaining),
        "period_end": str(period_end),
    }
    path = _quota_path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, sort_keys=True), encoding="utf-8")
    return {"remaining": int(remaining), "period_end": str(period_end)}


def quota_allows_http(tenant_id: str) -> bool:
    """Return True when the tenant's quota permits an HTTP provider call.

    Returns False when ``remaining`` is zero or negative.  Returns False
    when ``period_end`` is a valid UTC instant in the past.  An empty
    ``period_end`` counts as *not* expired, so a row with remaining units
    and no period end still allows HTTP.  Unparseable ``period_end``
    values are treated as not expired.
    """
    quota = get_quota(tenant_id)
    if int(quota["remaining"]) <= 0:
        return False
    period_end = str(quota.get("period_end", "")).strip()
    if not period_end:
        return True
    try:
        from datetime import datetime, timezone

        dt = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt < datetime.now(timezone.utc):
            return False
    except (ValueError, TypeError):
        pass
    return True


def consume_quota(tenant_id: str, n: int = 1) -> int:
    """Decrement *tenant_id*'s remaining quota by *n* and return the new value.

    The remaining value never drops below 0.  When no row exists yet the
    default remaining is 0, so consuming returns 0.  ``period_end`` is
    preserved across the decrement.
    """
    current = get_quota(tenant_id)
    new_remaining = max(0, int(current["remaining"]) - n)
    set_quota(tenant_id, remaining=new_remaining, period_end=current["period_end"])
    return new_remaining
