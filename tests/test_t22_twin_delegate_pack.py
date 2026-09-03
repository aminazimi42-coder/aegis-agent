"""T22 — Delegate pack for an assistant.

Covers:
- render_pack without a consented profile raises ValueError.
- After a T03 commit + ingest calendar meeting Standup: file exists,
  contains "Standup", and contains the written-approval header.
- After ingest email subject "Budget review": file contains "Budget review".
- After propose actions: file contains pending action title.
- After git commit for repo acme/core: file contains "acme/core".
- FastAPI 200 on POST /api/v1/twin/delegate/render.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_actions import propose_actions
from core.twin_delegate_pack import render_pack
from core.twin_events import ingest_event
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT22TwinDelegatePack(unittest.TestCase):
    """Delegate pack invariants."""

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

    def test_render_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            render_pack("no_profile_t22")

    def test_pack_contains_standup_and_approval_header(self) -> None:
        self._full_interview("t22a")
        ingest_event(
            "t22a",
            "calendar",
            "meeting",
            {"summary": "Standup", "start": "20260903T090000Z"},
        )

        result = render_pack("t22a")

        self.assertEqual(result["tenant_id"], "t22a")
        self.assertIn("path", result)

        pack_path = Path(result["path"])
        self.assertTrue(pack_path.exists(), f"missing file: {pack_path}")

        text = pack_path.read_text(encoding="utf-8")
        self.assertIn("Standup", text)
        self.assertIn(
            "Do not send mail or move money without my written approval.",
            text,
        )

    def test_pack_contains_email_subject_and_pending_action(self) -> None:
        self._full_interview("t22b")
        ingest_event(
            "t22b",
            "email",
            "message",
            {"from": "a@b.com", "subject": "Budget review"},
        )
        propose_actions("t22b")

        result = render_pack("t22b")
        text = Path(result["path"]).read_text(encoding="utf-8")

        self.assertIn("Budget review", text)
        self.assertIn("[proposed]", text)

    def test_pack_contains_repo(self) -> None:
        self._full_interview("t22c")
        ingest_event(
            "t22c",
            "git",
            "commit",
            {"repo": "acme/core", "sha": "aaa", "subject": "feat: init"},
        )

        result = render_pack("t22c")
        text = Path(result["path"]).read_text(encoding="utf-8")

        self.assertIn("acme/core", text)

    def test_pack_overwrites_on_second_call(self) -> None:
        self._full_interview("t22d")
        ingest_event(
            "t22d",
            "calendar",
            "meeting",
            {"summary": "Sync", "start": "20260903T100000Z"},
        )

        r1 = render_pack("t22d")
        text1 = Path(r1["path"]).read_text(encoding="utf-8")

        r2 = render_pack("t22d")
        text2 = Path(r2["path"]).read_text(encoding="utf-8")

        self.assertEqual(r1["path"], r2["path"])
        self.assertEqual(text1, text2)

    def test_fastapi_delegate_render_200(self) -> None:
        self._full_interview("t22e")
        ingest_event(
            "t22e",
            "calendar",
            "meeting",
            {"summary": "Review", "start": "20260903T110000Z"},
        )

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/delegate/render",
            json={"tenant_id": "t22e"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t22e")
        self.assertIn("path", body)

    def test_fastapi_delegate_render_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/delegate/render",
            json={"tenant_id": "no_profile_t22"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
