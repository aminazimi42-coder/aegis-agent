from __future__ import annotations

import json
import os
import sqlite3
from typing import Dict, List

DB_PATH = os.path.join(os.getcwd(), ".agents.db")


def _conn():
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """
        CREATE TABLE IF NOT EXISTS agents (
            name TEXT PRIMARY KEY,
            role TEXT,
            description TEXT,
            capabilities TEXT
        )
        """
        )


def save_agent(spec) -> None:
    init_db()
    with _conn() as c:
        c.execute(
            (
                "INSERT OR REPLACE INTO agents (name, role, description, "
                "capabilities) VALUES (?, ?, ?, ?)"
            ),
            (
                spec.name,
                spec.role,
                spec.description,
                json.dumps(spec.capabilities),
            ),
        )


def remove_agent(name: str) -> None:
    init_db()
    with _conn() as c:
        c.execute("DELETE FROM agents WHERE name = ?", (name,))


def list_agents() -> List[Dict[str, str]]:
    init_db()
    with _conn() as c:
        cur = c.execute("SELECT name, role, description, capabilities FROM agents")
        rows = cur.fetchall()
    result = []
    for r in rows:
        result.append(
            {
                "name": r[0],
                "role": r[1],
                "description": r[2],
                "capabilities": json.loads(r[3]),
            }
        )
    return result
