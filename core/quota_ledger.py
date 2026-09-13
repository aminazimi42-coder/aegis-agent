"""Local quota ledger outside execute (T156).

A single JSON file — ``$AEGIS_DATA_DIR/quota.json`` — tracks a monthly
allowance per tenant.  Counting happens **outside** ``execute``; the
ledger is consulted only by ``complete_safe`` and the operator status
surface.

File shape::

    {
      "<tenant_id>": {
        "tenant_id": "<tenant_id>",
        "period": "2026-09",
        "allowance": 100,
        "used": 5,
        "updated_at": "2026-09-13T12:00:00Z"
      }
    }

Fields per tenant row:

* ``tenant_id``  — string identifying the tenant
* ``period``     — calendar month in UTC (``YYYY-MM``)
* ``allowance``  — int, the monthly allowance
* ``used``       — int, units consumed so far this period
* ``updated_at`` — ISO-8601 UTC string of the last write

``remaining`` is ``max(allowance - used, 0)``.  When the file is
missing the default ``allowance`` is ``0`` — Echo-limited, not an
implicit paid pool.

The module never opens a socket.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_local_view import data_root


def _quota_path() -> Path:
    """Return the path to the single ``quota.json`` file."""
    return data_root() / "quota.json"


def _current_period() -> str:
    """Return the current calendar month in UTC as ``YYYY-MM``."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _load_all() -> dict[str, dict[str, Any]]:
    """Load the entire quota file; return ``{}`` when missing or invalid."""
    path = _quota_path()
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _save_all(data: dict[str, dict[str, Any]]) -> None:
    """Persist *data* as the quota file."""
    path = _quota_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _row(tenant_id: str) -> dict[str, Any]:
    """Return the row for *tenant_id* or a default-allowance row."""
    all_data = _load_all()
    row = all_data.get(tenant_id)
    if not isinstance(row, dict):
        return {
            "tenant_id": tenant_id,
            "period": _current_period(),
            "allowance": 0,
            "used": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    # Validate / coerce fields.
    try:
        allowance = int(row.get("allowance", 0))
    except (ValueError, TypeError):
        allowance = 0
    try:
        used = int(row.get("used", 0))
    except (ValueError, TypeError):
        used = 0
    period = row.get("period")
    if not isinstance(period, str) or not period:
        period = _current_period()
    return {
        "tenant_id": tenant_id,
        "period": period,
        "allowance": allowance,
        "used": used,
        "updated_at": str(row.get("updated_at", "")),
    }


def remaining(tenant_id: str) -> int:
    """Return ``max(allowance - used, 0)`` for *tenant_id*.

    When the quota file is missing the default ``allowance`` is ``0``
    so ``remaining`` is ``0`` — Echo-limited, not an implicit paid
    pool.
    """
    row = _row(tenant_id)
    return max(int(row["allowance"]) - int(row["used"]), 0)


def exhausted(tenant_id: str) -> bool:
    """Return ``True`` when ``remaining == 0``."""
    return remaining(tenant_id) == 0


def increment(tenant_id: str) -> int:
    """Add one ``used`` unit only when ``remaining > 0``.

    Returns the new ``remaining`` value.  When ``remaining`` is already
    ``0`` the call is a no-op and ``0`` is returned.
    """
    all_data = _load_all()
    row = all_data.get(tenant_id)
    if not isinstance(row, dict):
        row = {
            "tenant_id": tenant_id,
            "period": _current_period(),
            "allowance": 0,
            "used": 0,
            "updated_at": "",
        }
    try:
        allowance = int(row.get("allowance", 0))
    except (ValueError, TypeError):
        allowance = 0
    try:
        used = int(row.get("used", 0))
    except (ValueError, TypeError):
        used = 0
    rem = max(allowance - used, 0)
    if rem <= 0:
        # Already exhausted — do not go negative.
        row["used"] = used
        row["allowance"] = allowance
    else:
        row["used"] = used + 1
    row["tenant_id"] = tenant_id
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    all_data[tenant_id] = row
    _save_all(all_data)
    return max(allowance - int(row["used"]), 0)


def set_allowance(tenant_id: str, allowance: int, period: str | None = None) -> int:
    """Set the monthly ``allowance`` for *tenant_id* and return ``remaining``.

    ``used`` is preserved across the call.  ``period`` defaults to the
    current calendar month in UTC.  This is a convenience helper for
    tests and administrative scripts; it never opens a socket.
    """
    all_data = _load_all()
    row = all_data.get(tenant_id)
    if not isinstance(row, dict):
        row = {
            "tenant_id": tenant_id,
            "period": period or _current_period(),
            "allowance": int(allowance),
            "used": 0,
            "updated_at": "",
        }
    row["tenant_id"] = tenant_id
    row["allowance"] = int(allowance)
    row["period"] = period or row.get("period") or _current_period()
    try:
        used = int(row.get("used", 0))
    except (ValueError, TypeError):
        used = 0
    row["used"] = used
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    all_data[tenant_id] = row
    _save_all(all_data)
    return max(int(row["allowance"]) - int(row["used"]), 0)


def quota_state(tenant_id: str) -> str:
    """Return ``"ok"`` | ``"exhausted"`` | ``"unset"``.

    ``"unset"`` is returned when the quota file does not exist at all.
    ``"exhausted"`` when ``remaining == 0``.  ``"ok"`` otherwise.
    """
    path = _quota_path()
    if not path.is_file():
        return "unset"
    if exhausted(tenant_id):
        return "exhausted"
    return "ok"
