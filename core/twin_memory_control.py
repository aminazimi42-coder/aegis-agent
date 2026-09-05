"""Memory control list and forget (T44).

``show(tenant_id)`` writes ``work_products/{tenant_id}/memory.md`` listing
the profile keys that currently exist for the tenant (name, role, and any
other keys present — secrets are skipped).  ``forget(tenant_id, field)``
persists the forgotten field name in the SQLite ``forgotten`` table and
removes it from subsequent ``show`` output.

Both functions require a consented twin profile and raise
``ValueError("no consented profile")`` otherwise.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.twin_interview import get_latest_profile
from core.twin_persist import init_schema

# Keys that are metadata / secrets and should never appear in the
# memory-control listing.
_SKIP_KEYS: frozenset[str] = frozenset(
    {
        "profile_id",
        "fingerprint",
        "created_at",
        "updated_at",
        "consent",
        "version",
    }
)


def _db_path() -> Path:
    """Return the path to the SQLite database file."""
    return Path(os.getenv("AEGIS_DATA_DIR", "data")) / "aegis.sqlite"


def _connect():
    """Open a new connection to the SQLite database (creates the file)."""
    import sqlite3

    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _work_products_dir(tenant_id: str) -> Path:
    """Return the directory where work-product files for *tenant_id* live."""
    base = Path(os.getenv("AEGIS_DATA_DIR", "data"))
    return base / "work_products" / tenant_id


def _get_forgotten(tenant_id: str) -> list[str]:
    """Return the list of forgotten field names for *tenant_id*."""
    init_schema()

    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT field FROM forgotten WHERE tenant_id = ? ORDER BY field",
            (tenant_id,),
        ).fetchall()
        return [r["field"] for r in rows]
    finally:
        conn.close()


def _add_forgotten(tenant_id: str, field: str) -> None:
    """Persist a forgotten field name for *tenant_id*."""
    init_schema()

    conn = _connect()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO forgotten (tenant_id, field, at) "
            "VALUES (?, ?, ?)",
            (tenant_id, field, now),
        )
        conn.commit()
    finally:
        conn.close()


def _visible_fields(profile: dict[str, Any], forgotten: list[str]) -> list[str]:
    """Return the ordered list of profile keys to display.

    Skips metadata / secret keys and any field in *forgotten*.
    """
    skip = set(_SKIP_KEYS) | set(forgotten)
    fields: list[str] = []
    for key in ("name", "role"):
        if key in profile and key not in skip:
            fields.append(key)
    for key in profile:
        if key in skip or key in fields:
            continue
        fields.append(key)
    return fields


def _write_memory_md(
    tenant_id: str,
    fields: list[str],
    profile: dict[str, Any],
) -> Path:
    """Write ``memory.md`` for *tenant_id* and return its path."""
    out_dir = _work_products_dir(tenant_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "memory.md"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = [
        f"# Memory — {tenant_id}",
        "",
        f"_Generated: {now}_",
        "",
    ]
    if not fields:
        lines.append("_No profile fields available._")
        lines.append("")
    else:
        for field in fields:
            value = profile.get(field, "")
            heading = field.replace("_", " ").title()
            lines.append(f"## {heading}")
            lines.append("")
            lines.append(str(value) if value else "_(empty)_")
            lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def show(tenant_id: str) -> dict[str, Any]:
    """List the profile fields the twin has stored for *tenant_id*.

    Writes ``work_products/{tenant_id}/memory.md`` listing the profile keys
    that exist (name, role, and any other present keys — secrets skipped).
    Forgotten fields are omitted from the listing.

    Returns ``{tenant_id, path, fields}`` where *path* is the absolute path
    to ``memory.md`` and *fields* is the ordered list of visible field names.

    Raises ``ValueError("no consented profile")`` when *tenant_id* has no
    committed profile.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    forgotten = _get_forgotten(tenant_id)
    fields = _visible_fields(profile, forgotten)
    md_path = _write_memory_md(tenant_id, fields, profile)

    return {
        "tenant_id": tenant_id,
        "path": md_path.as_posix(),
        "fields": fields,
    }


def forget_all(tenant_id: str) -> dict[str, Any]:
    """Clear all active twin stores for *tenant_id* and write a deletion receipt.

    Clears:
    - All forgotten-field rows for this tenant (``forgotten`` table).
    - The visible memory listing (``work_products/{tenant_id}/memory.md``).
    - All ``twin_actions`` rows for this tenant.

    Neighbour tenants are never touched.

    Writes ``work_products/{tenant_id}/deletion_receipt.md`` containing the
    tenant_id and the UTC deletion time.

    Returns ``{tenant_id, receipt_path, cleared: True}`` where *receipt_path*
    is the absolute path to ``deletion_receipt.md``.
    """
    # 1. Clear forgotten rows for this tenant only.
    init_schema()
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM forgotten WHERE tenant_id = ?",
            (tenant_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # 2. Remove the visible memory listing (memory.md).
    out_dir = _work_products_dir(tenant_id)
    memory_md = out_dir / "memory.md"
    if memory_md.exists():
        memory_md.unlink()

    # 3. Delete this tenant's twin_actions rows (neighbour stays intact).
    from core.twin_actions import _ensure_schema as _ensure_actions_schema

    _ensure_actions_schema()
    from core.persistence import get_connection

    with get_connection() as conn2:
        conn2.execute(
            "DELETE FROM twin_actions WHERE tenant_id = ?",
            (tenant_id,),
        )

    # 4. Write the deletion receipt.
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = out_dir / "deletion_receipt.md"
    now_utc = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# Deletion Receipt — {tenant_id}",
        "",
        f"tenant_id: {tenant_id}",
        f"deleted_at: {now_utc}",
        "",
    ]
    receipt_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "tenant_id": tenant_id,
        "receipt_path": receipt_path.as_posix(),
        "cleared": True,
    }


def forget(tenant_id: str, field: str) -> dict[str, Any]:
    """Drop *field* from the memory listing for *tenant_id*.

    Persists the forgotten field name in the ``forgotten`` SQLite table.
    Overwrites ``memory.md`` with the updated listing.

    Returns ``{tenant_id, path, fields}`` — same shape as ``show``.

    Raises ``ValueError("no consented profile")`` when *tenant_id* has no
    committed profile.
    """
    profile = get_latest_profile(tenant_id)
    if profile is None:
        raise ValueError("no consented profile")

    _add_forgotten(tenant_id, field)
    forgotten = _get_forgotten(tenant_id)
    fields = _visible_fields(profile, forgotten)
    md_path = _write_memory_md(tenant_id, fields, profile)

    return {
        "tenant_id": tenant_id,
        "path": md_path.as_posix(),
        "fields": fields,
    }
