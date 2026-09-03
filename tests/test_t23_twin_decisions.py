"""T23 — Searchable yes/no decision log.

Covers:
- record() without a consented profile raises ValueError.
- After a T03 commit: record yes "Hire analyst" reason "bandwidth";
  list contains "Hire analyst"; query "bandwidth" returns 1.
- invalid decision raises ValueError.
- FastAPI POST 200 on /api/v1/twin/decisions.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_decisions import list_decisions, record
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT23TwinDecisions(unittest.TestCase):
    """Decision-log invariants."""

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

    def test_record_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            record("no_profile_t23", "Hire analyst", "yes", "bandwidth")

    def test_record_and_list_and_query(self) -> None:
        self._full_interview("t23a")

        result = record("t23a", "Hire analyst", "yes", "bandwidth")
        self.assertEqual(result["tenant_id"], "t23a")
        self.assertEqual(result["decision"], "yes")
        self.assertEqual(result["title"], "Hire analyst")
        self.assertEqual(result["reason"], "bandwidth")
        self.assertTrue(result["id"])

        # list contains the recorded decision.
        decisions = list_decisions("t23a")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["title"], "Hire analyst")

        # query "bandwidth" returns 1.
        queried = list_decisions("t23a", query="bandwidth")
        self.assertEqual(len(queried), 1)
        self.assertEqual(queried[0]["title"], "Hire analyst")

        # query that does not match returns 0.
        self.assertEqual(len(list_decisions("t23a", query="nomatch")), 0)

    def test_invalid_decision_raises(self) -> None:
        self._full_interview("t23b")
        with self.assertRaises(ValueError):
            record("t23b", "Promote X", "maybe", "uncertainty")

    def test_decision_log_md_written_on_record(self) -> None:
        self._full_interview("t23c")
        record("t23c", "Buy licenses", "yes", "team needs tools")
        record("t23c", "Hire contractor", "no", "budget freeze")

        log_path = Path(self._tmp) / "work_products" / "t23c" / "decision_log.md"
        self.assertTrue(log_path.exists())
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("Buy licenses", text)
        self.assertIn("Hire contractor", text)
        self.assertIn("YES", text)
        self.assertIn("NO", text)

    def test_fastapi_post_200(self) -> None:
        self._full_interview("t23d")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/decisions",
            json={
                "tenant_id": "t23d",
                "title": "Hire analyst",
                "decision": "yes",
                "reason": "bandwidth",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t23d")
        self.assertEqual(body["decision"], "yes")

    def test_fastapi_get_list(self) -> None:
        self._full_interview("t23e")
        record("t23e", "Migrate DB", "yes", "scaling")

        app = create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/twin/decisions/t23e?q=scaling")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["decisions"][0]["title"], "Migrate DB")

    def test_fastapi_post_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/decisions",
            json={
                "tenant_id": "no_profile_t23",
                "title": "Test",
                "decision": "yes",
                "reason": "test",
            },
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
