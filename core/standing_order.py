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


# ---------------------------------------------------------------------------#
# T219 — Specialist-name standing-order pin (tenant-bound SQLite)
# ---------------------------------------------------------------------------#

# The six specialist names — no seventh agent.
SPECIALIST_NAMES: tuple[str, ...] = (
    "Alina",
    "Kian",
    "Bita",
    "Aylin",
    "Ahmad",
    "Amin",
)


class StandingOrderUnknownError(ValueError):
    """Typed rejection when *specialist_name* is not one of the six names.

    T219 — the stable ``code`` attribute is ``"STANDING_ORDER_UNKNOWN"``.
    """

    code: str = "STANDING_ORDER_UNKNOWN"


def _ensure_pin_table() -> None:
    """Create the ``standing_order_pins`` table if it does not exist."""
    from core.persistence import get_connection

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS standing_order_pins (
                tenant_id   TEXT PRIMARY KEY,
                specialist  TEXT    NOT NULL
            )
            """
        )


def get_specialist_pin(tenant_id: str) -> str:
    """Return the pinned specialist name for *tenant_id*, or ``""``.

    T219 — the pin is tenant-bound SQLite.  A neighbor tenant's pin
    is never returned.  When no pin exists, returns an empty string.
    """
    _ensure_pin_table()
    from core.persistence import execute_scalar

    row = execute_scalar(
        "SELECT specialist FROM standing_order_pins WHERE tenant_id = ?",
        (tenant_id,),
    )
    return str(row) if row else ""


def set_specialist_pin(tenant_id: str, specialist_name: str) -> str:
    """Pin *specialist_name* as the security reviewer for *tenant_id*.

    T219 — *specialist_name* must be one of the six names
    (Alina, Kian, Bita, Aylin, Ahmad, Amin).  An unknown name raises
    :class:`StandingOrderUnknownError` with ``code = "STANDING_ORDER_UNKNOWN"``.

    The pin never auto-approves and never auto-executes.  It only
    surfaces as ``standing_order_hint`` on the next Propose so the
    operator sees the pinned specialist on the card.  Ahmad pin does
    not silence the other five rows — all six specialists still run.

    Returns the stored specialist name.
    """
    name = (specialist_name or "").strip()
    if name not in SPECIALIST_NAMES:
        raise StandingOrderUnknownError(
            f"unknown specialist: {specialist_name!r}"
        )
    _ensure_pin_table()
    from core.persistence import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO standing_order_pins (tenant_id, specialist) "
            "VALUES (?, ?) "
            "ON CONFLICT(tenant_id) DO UPDATE SET specialist = ?",
            (tenant_id, name, name),
        )
    return name


def clear_specialist_pin(tenant_id: str) -> str:
    """Clear the specialist pin for *tenant_id*.

    T219 — Forget clears the pin.  Returns an empty string when
    cleared (or when no pin existed).
    """
    _ensure_pin_table()
    from core.persistence import get_connection

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM standing_order_pins WHERE tenant_id = ?",
            (tenant_id,),
        )
    return ""


def specialist_pin_hint(tenant_id: str) -> str:
    """Return the standing-order hint for the next Propose, or ``""``.

    T219 — when a specialist pin exists for *tenant_id*, returns a
    short hint string like ``"Ahmad is the pinned security reviewer"``.
    When no pin exists, returns an empty string.  The hint is advisory
    text only — it never auto-approves or auto-executes.
    """
    name = get_specialist_pin(tenant_id)
    if not name:
        return ""
    return f"{name} is the pinned security reviewer"
