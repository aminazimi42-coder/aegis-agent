"""Standing-order pin — one short local string per tenant (T208).

A standing-order pin is a short local text string the operator pins for a
tenant.  When present, the next Propose and Weekly brief include that string
in the task text — they do **not** execute it.  An empty pin means no pin.

The pin is tenant-bound: a neighbor tenant's pin must not appear.  The pin
is stored under ``<AEGIS_DATA_DIR>/standing_orders/<tenant>.txt`` — a plain
text file, one line.  No cloud, no execute, no model.

T208 — the pin is included on the next Propose and Weekly brief by
appending it to the task text before the six specialists run.  It is not
executed, not approved, and not sent.
"""

from __future__ import annotations

from pathlib import Path


def _orders_dir() -> Path:
    """Return the standing-orders directory under the data root."""
    from core.twin_local_view import data_root

    root = data_root()
    d = root / "standing_orders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pin_path(tenant_id: str) -> Path:
    """Return the path to the pin file for *tenant_id*."""
    safe = tenant_id.replace("/", "_").replace("\\", "_")
    return _orders_dir() / f"{safe}.txt"


def save_pin(tenant_id: str, pin: str) -> str:
    """Save *pin* for *tenant_id*.

    An empty or whitespace-only *pin* clears the pin (no file).  The
    stored value is stripped and truncated to 200 characters.  Returns
    the stored value (empty string when cleared).
    """
    value = (pin or "").strip()[:200]
    path = _pin_path(tenant_id)
    if not value:
        # Empty pin means no pin — remove the file if it exists.
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return ""
    path.write_text(value + "\n", encoding="utf-8")
    return value


def get_pin(tenant_id: str) -> str:
    """Return the pin for *tenant_id*, or an empty string when none.

    The pin is tenant-bound — a neighbor's pin is never returned.
    """
    path = _pin_path(tenant_id)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return ""
    return text[:200]


def pin_suffix(tenant_id: str) -> str:
    """Return the pin suffix to append to the next task text.

    Returns ``" [pin: <value>]"`` when a pin exists, or an empty
    string when no pin is set.  The pin is included in the task text
    so the six specialists' proposals carry it; it is not executed.
    """
    pin = get_pin(tenant_id)
    if not pin:
        return ""
    return f" [pin: {pin}]"
