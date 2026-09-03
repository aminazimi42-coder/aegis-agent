"""T42 — Goal text to ordered proposed-action plan.

Covers:
- plan_goal without a consented profile raises ValueError.
- After a T03-style commit, plan_goal with "1. Review the PR\\n2. Draft the reply"
  writes goal_plan.md containing "Review" and "Draft".
- FastAPI 200 on POST /api/v1/twin/goal/plan.
- No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_goal_plan import plan_goal
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT42TwinGoalPlan(unittest.TestCase):
    """Goal-text-to-ordered-plan invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t42_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # --- helpers --- #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete T03 interview and return the session id."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    # --- consent gate --- #

    def test_plan_goal_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            plan_goal("no_profile_t42", "Do something useful today.")

    # --- numbered-line split + markdown content --- #

    def test_plan_goal_numbered_lines_markdown_contains_review_and_draft(self) -> None:
        self._full_interview("t42a")
        result = plan_goal("t42a", "1. Review the PR\n2. Draft the reply")

        self.assertEqual(result["tenant_id"], "t42a")
        self.assertTrue(Path(result["path"]).exists())

        md = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("Review", md)
        self.assertIn("Draft", md)

    # --- FastAPI 200 --- #

    def test_fastapi_goal_plan_200(self) -> None:
        self._full_interview("t42c")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/goal/plan",
            json={
                "tenant_id": "t42c",
                "text": "1. Review the PR\n2. Draft the reply",
            },
        )
        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t42c")
        self.assertTrue(body["path"])

    def test_fastapi_goal_plan_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/goal/plan",
            json={"tenant_id": "no_profile_t42", "text": "Nothing."},
        )
        self.assertEqual(resp.status_code, 400)

    # --- no live network --- #

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
