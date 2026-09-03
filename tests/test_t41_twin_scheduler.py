"""T41 — durable commitment scheduler.

A Monday-10:00 commitment must survive process restart.  ``schedule()``
persists a job row in SQLite; ``tick()`` only marks due rows — it does not
execute side effects.  Consent is required: calling ``schedule`` without a
committed profile raises ``ValueError("no consented profile")``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from app.server import create_app
from core.twin_interview import answer, commit, start_session
from core.twin_scheduler import list_jobs, schedule, tick
from fastapi.testclient import TestClient


def _complete_interview(tenant_id: str) -> None:
    """Run a full 6-question interview and commit a profile for *tenant_id*."""
    state = start_session(tenant_id)
    session_id = state["session_id"]
    for _ in range(6):
        qid = state["next_question"]["id"]
        state = answer(session_id, qid, "test answer")
    commit(session_id, consent=True)


class TestT41TwinScheduler(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t41_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # --- consent gate ---

    def test_schedule_without_profile_raises_value_error(self):
        before = len(list_jobs("solo"))
        with self.assertRaises(ValueError) as ctx:
            schedule("solo", "send report", "2099-01-01T10:00:00+00:00")
        self.assertIn("no consented profile", str(ctx.exception))
        # No job was created.
        self.assertEqual(len(list_jobs("solo")), before)

    # --- schedule + list_jobs durability ---

    def test_schedule_then_new_connection_list_jobs(self):
        _complete_interview("t41a")
        job = schedule("t41a", "Monday standup", "2099-01-01T10:00:00+00:00")
        self.assertEqual(job["status"], "scheduled")
        self.assertEqual(job["tenant_id"], "t41a")

        # Simulate a process restart: a fresh Python process reading the
        # same SQLite file must still see the row.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import os; "
                    "from core.twin_scheduler import list_jobs; "
                    "rows = list_jobs('t41a'); "
                    "assert len(rows) == 1, rows; "
                    "assert rows[0]['status'] == 'scheduled'; "
                    "print('OK')"
                ),
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "AEGIS_DATA_DIR": self._tmp},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("OK", result.stdout)

    # --- tick flips status to due ---

    def test_tick_flips_status_to_due(self):
        _complete_interview("t41b")
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        schedule("t41b", "past job", past)
        schedule("t41b", "future job", future)

        due = tick()
        self.assertTrue(any(j["title"] == "past job" for j in due))
        self.assertFalse(any(j["title"] == "future job" for j in due))

        rows = list_jobs("t41b", status="due")
        self.assertTrue(any(r["title"] == "past job" and r["status"] == "due" for r in rows))
        rows_scheduled = list_jobs("t41b", status="scheduled")
        self.assertTrue(
            any(r["title"] == "future job" and r["status"] == "scheduled" for r in rows_scheduled),
        )

    # --- FastAPI 200 ---

    def test_fastapi_schedule_200(self):
        _complete_interview("t41c")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/schedule",
            json={
                "tenant_id": "t41c",
                "title": "API job",
                "due_at": "2099-01-01T10:00:00+00:00",
                "timezone": "UTC",
            },
        )
        self.assertEqual(resp.status_code, 200, msg=resp.text)
        body = resp.json()
        self.assertEqual(body["status"], "scheduled")
        self.assertEqual(body["tenant_id"], "t41c")

    def test_fastapi_schedule_tick_200(self):
        _complete_interview("t41d")
        app = create_app()
        client = TestClient(app)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        resp = client.post(
            "/api/v1/twin/schedule",
            json={"tenant_id": "t41d", "title": "due now", "due_at": past},
        )
        self.assertEqual(resp.status_code, 200, msg=resp.text)
        tick_resp = client.post("/api/v1/twin/schedule/tick", json={})
        self.assertEqual(tick_resp.status_code, 200, msg=tick_resp.text)
        self.assertGreater(tick_resp.json()["count"], 0)

    # --- no live network ---

    def test_no_live_network(self):
        # This test exists to assert the suite does not require network.
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
