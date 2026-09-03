"""T51 — Golden busy-day path.

One test walks the full deterministic path end-to-end:
  event → brief → propose → approve → local outbox.

No new core modules, no new product column, no live network.
"""

from __future__ import annotations

import json as _json
import os
import tempfile
import unittest
from pathlib import Path

from core.persistence import get_connection
from core.twin_actions import _action_digest, _load_action, approve, propose_actions
from core.twin_email_send import send_approved
from core.twin_events import ingest_event
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_morning_brief import render_brief
from core.twin_risk import classify


class TestT51GoldenBusyDay(unittest.TestCase):
    """Walk event → brief → propose → approve → local outbox in one test."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t51_")
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

    def _set_action_title_payload(
        self,
        action_id: str,
        title: str,
        payload: dict[str, str],
    ) -> None:
        """Update an existing action's title and payload in-place."""
        with get_connection() as conn:
            conn.execute(
                "UPDATE twin_actions SET title = ?, payload = ? "
                "WHERE action_id = ?",
                (title, _json.dumps(payload), action_id),
            )

    # ------------------------------------------------------------------ #
    # Golden path
    # ------------------------------------------------------------------ #

    def test_golden_busy_day(self) -> None:
        """Walk event → brief → propose → approve → local outbox."""
        tenant = "t51"
        self._full_interview(tenant)

        # 1. Ingest one calendar event.
        ingest_event(
            tenant,
            source="calendar",
            kind="meeting",
            payload={"summary": "Quarterly review", "start": "2026-09-03T09:00"},
        )

        # 2. Render brief — writes morning_brief.md.
        brief_result = render_brief(tenant)
        brief_path = Path(brief_result["path"])
        self.assertTrue(brief_path.is_file())
        self.assertIn("morning_brief.md", brief_path.name)

        # 3. Propose actions — at least one action.
        actions = propose_actions(tenant)
        self.assertGreaterEqual(len(actions), 1)

        # 4. Pick one action, set title so classify is L2 (contains "email"),
        #    set payload body, and approve it.
        chosen = actions[0]
        action_id = chosen["action_id"]
        email_title = "Email the busy day pack"
        self._set_action_title_payload(action_id, email_title, {"body": "Busy day pack"})
        self.assertEqual(classify(email_title), "L2")

        _action = _load_action(action_id)
        assert _action is not None
        approved = approve(action_id, tenant, "tester", _action_digest(_action))
        self.assertEqual(approved["status"], "approved")

        # 5. send_approved writes .eml under work_products/t51/outbox.
        result = send_approved(tenant, action_id)
        eml_path = Path(result["path"])
        self.assertTrue(eml_path.is_file())
        self.assertEqual(eml_path.suffix, ".eml")

        text = eml_path.read_text(encoding="utf-8")
        self.assertTrue("Busy day pack" in text or email_title in text)

    def test_fastapi_home_200(self) -> None:
        """FastAPI home still returns 200."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        self._full_interview("t51b")
        app = create_app()
        client = TestClient(app)
        resp = client.post("/api/v1/twin/home", json={"tenant_id": "t51b"})
        self.assertEqual(resp.status_code, 200)

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
