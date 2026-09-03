"""Day-zero cognitive-twin interview engine.

Provides an ordered, stateful interview flow backed by SQLite so that a new
``TwinInterviewStore`` pointing at the same ``AEGIS_DATA_DIR`` sees committed
profiles.

Public functional API (operates on a shared default store)::

    from core.twin_interview import start_session, answer, commit

For explicit isolation pass ``store=`` a fresh ``TwinInterviewStore``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.persistence import get_connection
from core.twin_schema import TwinProfile

# ---------------------------------------------------------------------------#
# Question bank
# ---------------------------------------------------------------------------#

QUESTIONS: list[dict[str, str]] = [
    {"id": "q_role", "prompt": "What primary role do you perform?"},
    {"id": "q_decision_style", "prompt": "How do you make decisions under uncertainty?"},
    {"id": "q_tools", "prompt": "Which tools or platforms do you use daily?"},
    {"id": "q_risk", "prompt": "What is your risk posture?"},
    {"id": "q_ethics", "prompt": "What are your work ethics?"},
    {"id": "q_repos", "prompt": "Which repositories or projects are you responsible for?"},
]

_QUESTION_IDS: list[str] = [q["id"] for q in QUESTIONS]
_QUESTION_PROMPTS: dict[str, str] = {q["id"]: q["prompt"] for q in QUESTIONS}


# ---------------------------------------------------------------------------#
# Schema helpers
# ---------------------------------------------------------------------------#

def _ensure_schema() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS twin_sessions (
                session_id   TEXT PRIMARY KEY,
                tenant_id    TEXT NOT NULL,
                state        TEXT NOT NULL,
                created_at   TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS twin_profiles (
                profile_id    TEXT PRIMARY KEY,
                tenant_id     TEXT NOT NULL,
                version       INTEGER NOT NULL,
                consent       INTEGER NOT NULL,
                fingerprint   TEXT NOT NULL,
                layers        TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_twin_profiles_tenant
            ON twin_profiles (tenant_id, version)
            """
        )


# ---------------------------------------------------------------------------#
# Store
# ---------------------------------------------------------------------------#

class TwinInterviewStore:
    """Thread-safe store for twin-interview sessions and committed profiles."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        _ensure_schema()

    # ---- sessions ------------------------------------------------------- #

    def _save_session(self, session_id: str, tenant_id: str, state: dict[str, Any]) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO twin_sessions (session_id, tenant_id, state, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    session_id,
                    tenant_id,
                    json.dumps(state),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _load_session(self, session_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT state FROM twin_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return json.loads(row["state"])

    # ---- public API ----------------------------------------------------- #

    def start_session(self, tenant_id: str) -> dict[str, Any]:
        """Create a new interview session and return its initial state."""
        session_id = f"twin-{uuid4().hex[:12]}"
        state: dict[str, Any] = {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "answers": {},
            "current_index": 0,
            "complete": False,
            "next_question": {
                "id": _QUESTION_IDS[0],
                "prompt": _QUESTION_PROMPTS[_QUESTION_IDS[0]],
            },
        }
        with self._lock:
            self._ensure_schema()
            self._save_session(session_id, tenant_id, state)
        return state

    def answer(self, session_id: str, question_id: str, text: str) -> dict[str, Any]:
        """Record an answer and advance the session.

        Rejects if ``question_id`` is not the current expected question.
        """
        with self._lock:
            self._ensure_schema()
            state = self._load_session(session_id)
            if state is None:
                raise ValueError(f"unknown session: {session_id}")
            if state.get("complete"):
                return {"complete": True}
            current = state["next_question"]
            if question_id != current["id"]:
                raise ValueError(
                    f"expected question {current['id']!r}, got {question_id!r}"
                )
            state["answers"][question_id] = text
            state["current_index"] += 1
            idx = state["current_index"]
            if idx >= len(_QUESTION_IDS):
                state["complete"] = True
                state.pop("next_question", None)
            else:
                qid = _QUESTION_IDS[idx]
                state["next_question"] = {"id": qid, "prompt": _QUESTION_PROMPTS[qid]}
            self._save_session(session_id, state["tenant_id"], state)
            return state

    def commit(self, session_id: str, consent: bool) -> dict[str, Any]:
        """Commit a completed session as a versioned profile.

        Requires ``consent=True`` and a complete interview.
        Returns the serialised profile dict (with fingerprint).
        """
        if not consent:
            raise PermissionError("consent required")
        with self._lock:
            self._ensure_schema()
            state = self._load_session(session_id)
            if state is None:
                raise ValueError(f"unknown session: {session_id}")
            if not state.get("complete"):
                raise ValueError("interview not complete")
            tenant_id = state["tenant_id"]
            version = self._next_version(tenant_id)
            profile_id = f"profile-{uuid4().hex[:12]}"
            profile = TwinProfile.from_layers(
                tenant_id=tenant_id,
                profile_id=profile_id,
                version=version,
                consent=True,
                answers=state["answers"],
            )
            row = profile.to_dict()
            self._persist_profile(row)
            return row

    # ---- profiles ------------------------------------------------------- #

    def _next_version(self, tenant_id: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS v FROM twin_profiles WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            return int(row["v"])

    def _persist_profile(self, row: dict[str, Any]) -> None:
        layers = {
            "role": row["role"],
            "decision_style": row["decision_style"],
            "tools": row["tools"],
            "risk_posture": row["risk_posture"],
            "work_ethics": row["work_ethics"],
            "repositories": row["repositories"],
        }
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO twin_profiles "
                "(profile_id, tenant_id, version, consent, "
                "fingerprint, layers, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["profile_id"],
                    row["tenant_id"],
                    row["version"],
                    1 if row["consent"] else 0,
                    row["fingerprint"],
                    json.dumps(layers),
                    row["created_at"],
                    row["updated_at"],
                ),
            )

    def get_latest_profile(self, tenant_id: str) -> dict[str, Any] | None:
        """Return the latest committed profile for ``tenant_id`` or ``None``."""
        self._ensure_schema()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM twin_profiles WHERE tenant_id = ? ORDER BY version DESC LIMIT 1",
                (tenant_id,),
            ).fetchone()
            if row is None:
                return None
            layers = json.loads(row["layers"])
            return {
                "profile_id": row["profile_id"],
                "tenant_id": row["tenant_id"],
                "version": row["version"],
                "consent": bool(row["consent"]),
                "fingerprint": row["fingerprint"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                **layers,
            }


# ---------------------------------------------------------------------------#
# Default store + functional wrappers
# ---------------------------------------------------------------------------#

_default_store: TwinInterviewStore | None = None
_default_lock = threading.Lock()


def _get_default_store() -> TwinInterviewStore:
    global _default_store
    if _default_store is None:
        with _default_lock:
            if _default_store is None:
                _default_store = TwinInterviewStore()
    return _default_store


def start_session(tenant_id: str) -> dict[str, Any]:
    """Start a new interview session (uses the default store)."""
    return _get_default_store().start_session(tenant_id)


def answer(session_id: str, question_id: str, text: str) -> dict[str, Any]:
    """Record an answer (uses the default store)."""
    return _get_default_store().answer(session_id, question_id, text)


def commit(session_id: str, consent: bool) -> dict[str, Any]:
    """Commit a session as a profile (uses the default store)."""
    return _get_default_store().commit(session_id, consent)


def get_latest_profile(tenant_id: str) -> dict[str, Any] | None:
    """Return the latest committed profile (uses the default store)."""
    return _get_default_store().get_latest_profile(tenant_id)
