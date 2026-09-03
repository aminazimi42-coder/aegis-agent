"""T07 — Production integrity capstone.

Covers:
- platform_status version, agent_count, agents, llm_provider.
- FastAPI GET /api/v1/platform/status 200.
- End-to-end walk: interview -> event -> digest -> propose -> approve -> execute.
- All isolated with AEGIS_DATA_DIR temp dir; no live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from app.server import create_app
from core.platform_status import platform_status
from core.twin_actions import _action_digest, _load_action, approve, execute, propose_actions
from core.twin_evolution import evolve, weekly_digest
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT07PlatformStatus(unittest.TestCase):
    """Honest platform status surface."""

    def test_platform_status_keys(self) -> None:
        s = platform_status()
        self.assertEqual(s["version"], "1.0.0-rc1")
        self.assertEqual(s["agent_count"], 6)
        self.assertIn("Ahmad", s["agents"])
        self.assertIn("Amin", s["agents"])
        self.assertEqual(len(s["agents"]), 6)
        self.assertIn("echo", s["llm_provider"].lower())
        self.assertIs(s["twin_routes"], True)
        self.assertEqual(s["persistence"], "sqlite")

    def test_platform_status_no_marketing(self) -> None:
        s = platform_status()
        blob = str(s).lower()
        self.assertNotIn("enterprise agi", blob)

    def test_fastapi_platform_status_200(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/platform/status")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["version"], "1.0.0-rc1")
        self.assertEqual(body["agent_count"], 6)
        self.assertEqual(len(body["agents"]), 6)
        self.assertIn("echo", body["llm_provider"].lower())


class TestT07E2EIntegrity(unittest.TestCase):
    """End-to-end walk: interview -> event -> digest -> propose -> approve -> execute."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    def test_full_walk_without_network(self) -> None:
        tenant = "t7e2e"

        # 1. Start + 6 answers + commit with consent.
        session = start_session(tenant)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        profile = commit(sid, True)
        self.assertTrue(profile["consent"])

        # 2. Ingest a git commit event + evolve.
        from core.twin_events import ingest_event

        event = ingest_event(
            tenant_id=tenant,
            source="git",
            kind="commit",
            payload={"repo": "aegis-agent", "sha": "abc123", "subject": "test"},
        )
        evolved = evolve(tenant, event)
        self.assertIsNotNone(evolved)

        # 3. weekly_digest event_count >= 1.
        digest = weekly_digest(tenant)
        self.assertGreaterEqual(digest["event_count"], 1)

        # 4. propose_actions >= 1.
        actions = propose_actions(tenant)
        self.assertGreaterEqual(len(actions), 1)
        first_id = actions[0]["action_id"]

        # 5. Execute before approve raises PermissionError.
        with self.assertRaises(PermissionError):
            execute(first_id)

        # 6. Approve then execute -> status executed.
        _action = _load_action(first_id)
        assert _action is not None
        approved = approve(first_id, tenant, "tester", _action_digest(_action))
        self.assertEqual(approved["status"], "approved")
        executed = execute(first_id)
        self.assertEqual(executed["status"], "executed")


if __name__ == "__main__":
    unittest.main()
