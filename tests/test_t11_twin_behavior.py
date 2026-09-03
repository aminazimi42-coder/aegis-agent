"""T11 — Versioned behavioral memory from twin events.

Covers:
- rebuild without a consented profile raises ValueError.
- After a T03-style commit + one git ingest_event: rebuild event_count >= 1,
  version == 1.
- Second rebuild with no new events: version stays 1.
- FastAPI GET after rebuild returns 200.
- get_behavior returns None when no snapshot exists.
- No live network / no LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from app.server import create_app
from core.twin_behavior import get_behavior, rebuild
from core.twin_events import ingest_event
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT11TwinBehavior(unittest.TestCase):
    """Versioned behavioral snapshot invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete T03 interview and return the session id."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_rebuild_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            rebuild("no_profile_t11")

    def test_rebuild_after_commit_and_event_count_and_version(self) -> None:
        self._full_interview("t11a")
        ingest_event(
            "t11a",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "aaa", "subject": "feat: init"},
        )
        snap = rebuild("t11a")
        self.assertGreaterEqual(snap["version"], 1)
        self.assertEqual(snap["version"], 1)
        self.assertGreaterEqual(snap["snapshot"]["event_count"], 1)
        self.assertIn("git", snap["snapshot"]["sources"])

    def test_second_rebuild_with_no_new_events_keeps_version(self) -> None:
        self._full_interview("t11b")
        ingest_event(
            "t11b",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "bbb", "subject": "fix: bug"},
        )
        first = rebuild("t11b")
        self.assertEqual(first["version"], 1)
        second = rebuild("t11b")
        self.assertEqual(second["version"], 1)

    def test_get_behavior_returns_none_when_no_snapshot(self) -> None:
        self.assertIsNone(get_behavior("never_t11"))

    def test_get_behavior_returns_snapshot_after_rebuild(self) -> None:
        self._full_interview("t11c")
        ingest_event(
            "t11c",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "ccc", "subject": "feat: init"},
        )
        rebuild("t11c")
        stored = get_behavior("t11c")
        assert stored is not None
        self.assertEqual(stored["tenant_id"], "t11c")
        self.assertGreaterEqual(stored["snapshot"]["event_count"], 1)

    def test_fastapi_get_behavior_200_after_rebuild(self) -> None:
        self._full_interview("t11d")
        ingest_event(
            "t11d",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "ddd", "subject": "feat: init"},
        )
        app = create_app()
        client = TestClient(app)

        # Rebuild via API.
        resp = client.post(
            "/api/v1/twin/behavior/rebuild",
            json={"tenant_id": "t11d"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(body["version"], 1)
        self.assertGreaterEqual(body["snapshot"]["event_count"], 1)

        # GET the stored snapshot.
        resp2 = client.get("/api/v1/twin/behavior/t11d")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["tenant_id"], "t11d")

    def test_fastapi_get_behavior_404_when_missing(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/twin/behavior/missing_t11")
        self.assertEqual(resp.status_code, 404)

    def test_fastapi_rebuild_without_profile_400(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/behavior/rebuild",
            json={"tenant_id": "no_profile_t11"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_rebuild_version_increments_on_new_event(self) -> None:
        self._full_interview("t11e")
        ingest_event(
            "t11e",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "eee", "subject": "feat: a"},
        )
        first = rebuild("t11e")
        self.assertEqual(first["version"], 1)

        # Add a new event → snapshot changes → version bumps.
        ingest_event(
            "t11e",
            "git",
            "commit",
            {"repo": "acme/other", "sha": "fff", "subject": "feat: b"},
        )
        second = rebuild("t11e")
        self.assertEqual(second["version"], 2)
        self.assertGreaterEqual(second["snapshot"]["event_count"], 2)


if __name__ == "__main__":
    unittest.main()
