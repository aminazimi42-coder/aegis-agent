"""T03 — Day-0 cognitive twin interview tests.

Covers:
- Full flow: start → six answers in order → commit consent=True → profile v1 with fingerprint.
- Wrong question_id is rejected.
- Commit consent=False raises PermissionError.
- A new store instance with the same AEGIS_DATA_DIR sees the committed profile.
- FastAPI test client: start, answer all six, commit, GET profile 200.
- No live LLM / network.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from app.server import create_app
from core.twin_interview import (
    QUESTIONS,
    TwinInterviewStore,
)
from fastapi.testclient import TestClient


class TestT03CognitiveTwin(unittest.TestCase):
    """End-to-end interview flow and invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_full_flow_creates_versioned_profile_with_fingerprint(self) -> None:
        store = TwinInterviewStore()
        session = store.start_session("t1")
        sid = session["session_id"]
        self.assertEqual(session["next_question"]["id"], "q_role")
        self.assertFalse(session["complete"])

        # Answer all six questions in order.
        state = None
        for q in QUESTIONS:
            state = store.answer(sid, q["id"], f"ans-{q['id']}")
        self.assertIsNotNone(state)
        self.assertTrue(state["complete"])

        profile = store.commit(sid, consent=True)
        self.assertEqual(profile["version"], 1)
        self.assertEqual(profile["tenant_id"], "t1")
        self.assertTrue(profile["consent"])
        self.assertTrue(profile["fingerprint"])
        self.assertEqual(len(profile["fingerprint"]), 64)  # sha256 hex
        # Layer fields are populated.
        self.assertEqual(profile["role"], "ans-q_role")
        self.assertEqual(profile["repositories"], "ans-q_repos")

    def test_wrong_question_id_is_rejected(self) -> None:
        store = TwinInterviewStore()
        session = store.start_session("t1")
        sid = session["session_id"]
        # First expected is q_role; try answering q_tools instead.
        with self.assertRaises(ValueError):
            store.answer(sid, "q_tools", "wrong order")

    def test_commit_without_consent_raises_permission_error(self) -> None:
        store = TwinInterviewStore()
        session = store.start_session("t1")
        sid = session["session_id"]
        for q in QUESTIONS:
            store.answer(sid, q["id"], f"ans-{q['id']}")
        with self.assertRaises(PermissionError):
            store.commit(sid, consent=False)

    def test_new_store_sees_committed_profile(self) -> None:
        store_a = TwinInterviewStore()
        session = store_a.start_session("t1")
        sid = session["session_id"]
        for q in QUESTIONS:
            store_a.answer(sid, q["id"], f"ans-{q['id']}")
        store_a.commit(sid, consent=True)

        store_b = TwinInterviewStore()
        profile = store_b.get_latest_profile("t1")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["version"], 1)
        self.assertEqual(profile["role"], "ans-q_role")

    def test_fastapi_flow_start_answer_commit_get_200(self) -> None:
        app = create_app()
        client = TestClient(app)

        # Start session.
        resp = client.post(
            "/api/v1/twin/session/start", json={"tenant_id": "t1"}
        )
        self.assertEqual(resp.status_code, 200)
        sid = resp.json()["session_id"]

        # Answer all six.
        for q in QUESTIONS:
            r = client.post(
                f"/api/v1/twin/session/{sid}/answer",
                json={"question_id": q["id"], "text": f"ans-{q['id']}"},
            )
            self.assertEqual(r.status_code, 200)

        # Commit with consent.
        r = client.post(
            f"/api/v1/twin/session/{sid}/commit", json={"consent": True}
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["version"], 1)

        # GET profile.
        r = client.get("/api/v1/twin/profile/t1")
        self.assertEqual(r.status_code, 200)
        profile = r.json()
        self.assertEqual(profile["version"], 1)
        self.assertEqual(profile["role"], "ans-q_role")
        self.assertTrue(profile["fingerprint"])

    def test_get_profile_404_when_no_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        r = client.get("/api/v1/twin/profile/nonexistent")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
