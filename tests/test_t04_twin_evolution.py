"""T04 — Twin live-evolution loop tests.

Covers:
- ingest without a consented profile raises ValueError.
- After a T03-style commit, ingesting a git-commit event appends the repo
  and bumps the profile version to 2.
- A second identical event does not bump the version.
- weekly_digest returns event_count >= 1.
- FastAPI client: event POST 200, digest GET 200.
- All isolated with AEGIS_DATA_DIR temp dir; no live LLM / network.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from app.server import create_app
from core.twin_events import ingest_event
from core.twin_evolution import evolve, weekly_digest
from core.twin_interview import QUESTIONS, commit, start_session
from fastapi.testclient import TestClient


class TestT04TwinEvolution(unittest.TestCase):
    """Deterministic evolution + digest invariants."""

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
            from core.twin_interview import answer

            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_ingest_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            ingest_event("no_profile_t", "git", "commit", {"repo": "acme/core"})

    def test_git_commit_appends_repo_and_bumps_version_to_2(self) -> None:
        self._full_interview("t4a")
        event = ingest_event("t4a", "git", "commit", {"repo": "acme/core"})
        profile = evolve("t4a", event)
        self.assertEqual(profile["version"], 2)
        self.assertIn("acme/core", profile["repositories"])

    def test_second_identical_event_does_not_bump_version(self) -> None:
        self._full_interview("t4b")
        event1 = ingest_event("t4b", "git", "commit", {"repo": "acme/core"})
        profile1 = evolve("t4b", event1)
        self.assertEqual(profile1["version"], 2)

        event2 = ingest_event("t4b", "git", "commit", {"repo": "acme/core"})
        profile2 = evolve("t4b", event2)
        self.assertEqual(profile2["version"], 2)

    def test_weekly_digest_returns_event_count_ge_1(self) -> None:
        self._full_interview("t4c")
        ingest_event("t4c", "git", "commit", {"repo": "acme/core"})
        evolve("t4c", ingest_event("t4c", "git", "commit", {"repo": "acme/core"}))
        digest = weekly_digest("t4c")
        self.assertGreaterEqual(digest["event_count"], 1)
        self.assertEqual(digest["tenant_id"], "t4c")
        self.assertIn("acme/core", digest["repos"])

    def test_fastapi_event_200_and_digest_200(self) -> None:
        # Run interview directly so the API digest can find the profile.
        self._full_interview("t4d")
        app = create_app()
        client = TestClient(app)

        # POST event.
        resp = client.post(
            "/api/v1/twin/events",
            json={
                "tenant_id": "t4d",
                "source": "git",
                "kind": "commit",
                "payload": {"repo": "acme/core"},
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("event", body)
        self.assertIn("profile", body)

        # GET digest.
        resp2 = client.get("/api/v1/twin/digest/t4d")
        self.assertEqual(resp2.status_code, 200)
        digest = resp2.json()
        self.assertGreaterEqual(digest["event_count"], 1)

    def test_fastapi_event_without_profile_returns_400(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/events",
            json={
                "tenant_id": "no_tenant",
                "source": "git",
                "kind": "commit",
                "payload": {"repo": "x"},
            },
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
