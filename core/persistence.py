"""SQLite persistence layer for the Aegis Agent platform.

All durable state (evidence ledger entries, task records) is stored in a single
SQLite database file located at ``{AEGIS_DATA_DIR or data}/aegis.sqlite``.
The directory is created on first access.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

_DB_NAME = "aegis.sqlite"


def _data_dir() -> Path:
    """Return the data directory, honouring ``AEGIS_DATA_DIR``.

    Falls back to ``./data`` when the env var is not set.
    """
    raw = os.getenv("AEGIS_DATA_DIR", "data")
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    """Return the absolute path to the SQLite database file."""
    return _data_dir() / _DB_NAME


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row factory set to ``sqlite3.Row``."""
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def execute_scalar(sql: str, params: tuple[Any, ...] = ()) -> Any:
    """Execute a scalar query and return the first column of the first row."""
    with get_connection() as conn:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None
