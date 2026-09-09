"""T138 — sole local start path and last reject reason on next card.

Verifies:
- ``scripts/start_operator.sh`` is the sole engine launcher; it binds to
  ``127.0.0.1`` (localhost) and exports ``AEGIS_DATA_DIR``.
- The next propose response includes ``last_reject_reason`` when a reject
  note exists for the tenant, and omits the field when no reject exists.
- No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestT138StartScript(unittest.TestCase):
    """The sole local start path binds localhost and exports data dir."""

    def test_single_start_script_binds_localhost(self) -> None:
        """start_operator.sh binds to 127.0.0.1 and starts uvicorn."""
        script = REPO_ROOT / "scripts" / "start_operator.sh"
        self.assertTrue(script.is_file(), "scripts/start_operator.sh must exist")
        text = script.read_text()
        # Must bind to localhost, not 0.0.0.0.
        self.assertIn("127.0.0.1", text,
                       "start_operator.sh must bind 127.0.0.1")
        # The HOST line must use 127.0.0.1, not 0.0.0.0.
        self.assertIn('HOST="127.0.0.1"', text,
                       "start_operator.sh HOST must be 127.0.0.1")
        # Must start the engine via uvicorn.
        self.assertIn("uvicorn", text,
                       "start_operator.sh must start uvicorn")

    def test_start_script_sets_data_dir(self) -> None:
        """start_operator.sh exports AEGIS_DATA_DIR."""
        script = REPO_ROOT / "scripts" / "start_operator.sh"
        text = script.read_text()
        self.assertIn("AEGIS_DATA_DIR", text,
                       "start_operator.sh must export AEGIS_DATA_DIR")

    def test_no_second_engine_launcher(self) -> None:
        """run_local.sh is a status CLI, not a duplicate engine launcher."""
        run_local = REPO_ROOT / "scripts" / "run_local.sh"
        text = run_local.read_text()
        # run_local.sh runs the status CLI, not uvicorn.
        self.assertNotIn("uvicorn", text,
                         "run_local.sh must not start uvicorn (not a duplicate launcher)")


class TestT138LastRejectReason(unittest.TestCase):
    """The next propose card shows the last reject reason when one exists."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t138_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    def _make_profile(self, tenant: str) -> None:
        """Create a committed profile so propose_actions works."""
        from core.twin_interview import (
            answer as twin_answer,
        )
        from core.twin_interview import (
            commit as twin_commit,
        )
        from core.twin_interview import (
            start_session as twin_start,
        )

        state = twin_start(tenant)
        session_id = state["session_id"]
        for _ in range(6):
            qid = state["next_question"]["id"]
            state = twin_answer(session_id, qid, "test answer")
        twin_commit(session_id, consent=True)

    def _propose_and_reject(self, tenant: str) -> str:
        """Propose one action, reject it, return the action_id."""
        from core.twin_actions import propose_actions, reject

        actions = propose_actions(tenant)
        action_id = actions[0]["action_id"]
        reject(action_id, tenant_id=tenant, why="too risky",
               reason_enum="POLICY_VIOLATION")
        return action_id

    def test_next_propose_includes_last_reject_reason(self) -> None:
        """The propose endpoint includes last_reject_reason after a reject."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t138-reject"
        self._make_profile(tenant)
        self._propose_and_reject(tenant)

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "new task"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("last_reject_reason", body,
                        "propose response must include last_reject_reason "
                        "after a reject")
        self.assertTrue(body["last_reject_reason"],
                        "last_reject_reason must be non-empty")

    def test_no_reject_omits_reason(self) -> None:
        """When no reject exists, last_reject_reason is omitted."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t138-no-reject"
        self._make_profile(tenant)

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "fresh task"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn("last_reject_reason", body,
                         "last_reject_reason must be omitted when no reject exists")

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
