"""Local SQLite backup and restore for a single tenant (T69).

``backup_tenant(tenant_id, dest)`` snapshots the tenant's profile rows,
twin_action rows, twin_feedback rows, jobs rows, and any receipt files
under ``work_products/{tenant_id}/receipts`` into a local ``.zip`` archive.
``restore_tenant(tenant_id, src)`` restores exactly that tenant from the
archive, leaving neighbour tenants untouched.

No network calls are made.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from core.persistence import get_connection

# Tables that carry a ``tenant_id`` column and should be included in the
# tenant-scoped snapshot.  Each entry is (table_name, tenant_column).
_TENANT_TABLES: list[tuple[str, str]] = [
    ("twin_profiles", "tenant_id"),
    ("twin_actions", "tenant_id"),
    ("twin_feedback", "tenant_id"),
    ("jobs", "tenant_id"),
]

_BACKUP_DB_NAME = "backup.sqlite"
_RECEIPTS_DIR_NAME = "receipts"


# ---------------------------------------------------------------------------#
# Helpers
# ---------------------------------------------------------------------------#

def _data_dir() -> Path:
    """Return the AEGIS_DATA_DIR path."""
    return Path(os.getenv("AEGIS_DATA_DIR", "data"))


def _receipts_dir(tenant_id: str) -> Path:
    """Return the on-disk receipts directory for *tenant_id*."""
    return _data_dir() / "work_products" / tenant_id / "receipts"


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Return the column names of *table* in *conn*."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Return True when *table* exists in *conn*."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------#
# Backup
# ---------------------------------------------------------------------------#

def backup_tenant(tenant_id: str, dest: Path) -> Path:
    """Snapshot *tenant_id* state into a local ``.zip`` archive at *dest*.

    The archive contains:
    - ``backup.sqlite`` — a SQLite DB with the tenant's rows from
      ``twin_profiles``, ``twin_actions``, ``twin_feedback``, and ``jobs``.
    - ``receipts/`` — any ``*.md`` receipt files from
      ``work_products/{tenant_id}/receipts/``.

    Returns the path to the written archive.  *dest* must end with
    ``.zip`` and reside under ``AEGIS_DATA_DIR``.
    """
    dest = Path(dest)
    if dest.suffix != ".zip":
        raise ValueError("dest must end with .zip")
    data_dir = _data_dir()
    # Resolve dest relative to AEGIS_DATA_DIR when not absolute.
    if not dest.is_absolute():
        dest = data_dir / dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Build the backup SQLite DB in a temp file.
    tmp_fd, tmp_db = tempfile.mkstemp(suffix=".sqlite")
    os.close(tmp_fd)
    tmp_db_path = Path(tmp_db)
    try:
        backup_conn = sqlite3.connect(str(tmp_db_path))
        source_conn = get_connection()
        try:
            for table, tcol in _TENANT_TABLES:
                if not _table_exists(source_conn, table):
                    continue
                cols = _table_columns(source_conn, table)
                # Create the same table schema in the backup DB.
                create_sql = (
                    f"CREATE TABLE {table} ({', '.join(cols)})"
                )
                backup_conn.execute(create_sql)
                # Copy only this tenant's rows.
                placeholders = ", ".join("?" for _ in cols)
                col_list = ", ".join(cols)
                rows = source_conn.execute(
                    f"SELECT {col_list} FROM {table} WHERE {tcol} = ?",
                    (tenant_id,),
                ).fetchall()
                if rows:
                    backup_conn.executemany(
                        f"INSERT INTO {table} ({col_list}) "
                        f"VALUES ({placeholders})",
                        [tuple(r) for r in rows],
                    )
            backup_conn.commit()
        finally:
            source_conn.close()
            backup_conn.close()

        # Write the zip archive.
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_db_path, _BACKUP_DB_NAME)
            # Include receipt files if they exist.
            rdir = _receipts_dir(tenant_id)
            if rdir.is_dir():
                for fpath in sorted(rdir.rglob("*")):
                    if fpath.is_file():
                        arcname = (
                            f"{_RECEIPTS_DIR_NAME}/"
                            f"{fpath.relative_to(rdir).as_posix()}"
                        )
                        zf.write(fpath, arcname)
    finally:
        tmp_db_path.unlink(missing_ok=True)

    return dest


# ---------------------------------------------------------------------------#
# Restore
# ---------------------------------------------------------------------------#

def restore_tenant(tenant_id: str, src: Path) -> dict[str, Any]:
    """Restore *tenant_id* from a ``.zip`` archive at *src*.

    Overwrites only the rows for *tenant_id* in ``twin_profiles``,
    ``twin_actions``, ``twin_feedback``, and ``jobs``.  Restores receipt
    files under ``work_products/{tenant_id}/receipts/``.  Neighbour tenants
    are untouched.

    Returns a dict with per-table restored row counts and receipt file count.
    """
    src = Path(src)
    if src.suffix != ".zip":
        raise ValueError("src must end with .zip")
    if not src.exists():
        raise FileNotFoundError(f"backup archive not found: {src}")

    tmp_fd, tmp_db = tempfile.mkstemp(suffix=".sqlite")
    os.close(tmp_fd)
    tmp_db_path = Path(tmp_db)
    # Remove the temp file so zipfile can extract cleanly to that name.
    tmp_db_path.unlink()
    try:
        # Extract backup.sqlite to the temp dir.
        with zipfile.ZipFile(src, "r") as zf:
            zf.extract(_BACKUP_DB_NAME, tmp_db_path.parent)
        extracted_db = tmp_db_path.parent / _BACKUP_DB_NAME
        if extracted_db != tmp_db_path:
            extracted_db.replace(tmp_db_path)

        backup_conn = sqlite3.connect(str(tmp_db_path))
        backup_conn.row_factory = sqlite3.Row
        dest_conn = get_connection()
        try:
            result: dict[str, Any] = {}

            for table, tcol in _TENANT_TABLES:
                if not _table_exists(dest_conn, table):
                    # Table doesn't exist in the live DB yet — create it
                    # using the backup schema as a template.
                    if _table_exists(backup_conn, table):
                        cols = _table_columns(backup_conn, table)
                        dest_conn.execute(
                            f"CREATE TABLE {table} "
                            f"({', '.join(cols)})"
                        )
                    else:
                        result[table] = 0
                        continue

                if not _table_exists(backup_conn, table):
                    result[table] = 0
                    continue

                # Delete existing rows for this tenant.
                dest_conn.execute(
                    f"DELETE FROM {table} WHERE {tcol} = ?",
                    (tenant_id,),
                )

                # Copy rows from the backup.
                cols = _table_columns(backup_conn, table)
                col_list = ", ".join(cols)
                placeholders = ", ".join("?" for _ in cols)
                rows = backup_conn.execute(
                    f"SELECT {col_list} FROM {table}"
                ).fetchall()
                if rows:
                    dest_conn.executemany(
                        f"INSERT INTO {table} ({col_list}) "
                        f"VALUES ({placeholders})",
                        [tuple(r) for r in rows],
                    )
                dest_conn.commit()
                result[table] = len(rows)

            # Restore receipt files.
            rdir = _receipts_dir(tenant_id)
            receipt_count = 0
            with zipfile.ZipFile(src, "r") as zf:
                receipt_names = [
                    n for n in zf.namelist()
                    if n.startswith(f"{_RECEIPTS_DIR_NAME}/")
                ]
                if receipt_names:
                    # Clear existing receipts for this tenant first.
                    if rdir.is_dir():
                        for fpath in rdir.rglob("*"):
                            if fpath.is_file():
                                fpath.unlink()
                        # Remove empty dirs.
                        for sub in sorted(
                            rdir.rglob("*"), reverse=True
                        ):
                            if sub.is_dir():
                                sub.rmdir()
                    rdir.mkdir(parents=True, exist_ok=True)
                    for name in receipt_names:
                        rel = name[len(_RECEIPTS_DIR_NAME) + 1:]
                        if not rel:
                            continue
                        out_path = rdir / rel
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        data = zf.read(name)
                        out_path.write_bytes(data)
                        receipt_count += 1
            result["receipts"] = receipt_count
            result["tenant_id"] = tenant_id
            return result
        finally:
            backup_conn.close()
            dest_conn.close()
    finally:
        tmp_db_path.unlink(missing_ok=True)
