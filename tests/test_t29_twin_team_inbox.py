"""T29 — Team inbox triage from a local chat export.

Covers:
- triage() without a consented profile raises ValueError.
- triage() with a missing export file raises ValueError.
- After a T03 commit, a .txt export line "Need the board pack tonight":
  team_inbox.md contains "board pack".
- .jsonl export with text/body fields.
- FastAPI 200 on POST /api/v1/twin/team/inbox.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_team_inbox import triage
from fastapi.testclient import TestClient


class TestT29TwinTeamInbox(unittest.TestCase):
    """Team-inbox triage invariants."""

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

    def test_triage_without_profile_raises_value_error(self) -> None:
        export = Path(self._tmp) / "chat.txt"
        export.write_text("hello", encoding="utf-8")
        with self.assertRaises(ValueError):
            triage("no_profile_t29", str(export))

    def test_triage_missing_export_raises_value_error(self) -> None:
        self._full_interview("t29b")
        with self.assertRaises(ValueError):
            triage("t29b", str(Path(self._tmp) / "nonexistent.txt"))

    def test_triage_txt_writes_board_pack(self) -> None:
        self._full_interview("t29c")
        export = Path(self._tmp) / "team_chat.txt"
        export.write_text(
            "Need the board pack tonight\n"
            "Another message here\n",
            encoding="utf-8",
        )

        result = triage("t29c", str(export))

        self.assertEqual(result["tenant_id"], "t29c")
        self.assertEqual(result["count"], 2)
        inbox_path = Path(result["path"])
        self.assertTrue(inbox_path.exists())

        text = inbox_path.read_text(encoding="utf-8")
        self.assertIn("board pack", text)
        self.assertIn("Need the board pack tonight", text)
        self.assertIn("1. Need the board pack tonight", text)

    def test_triage_jsonl_writes_body(self) -> None:
        self._full_interview("t29d")
        export = Path(self._tmp) / "team_chat.jsonl"
        lines = [
            json.dumps({"text": "Standup at 9am"}),
            json.dumps({"body": "Ship the release"}),
            json.dumps({"other": "ignored"}),
        ]
        export.write_text("\n".join(lines), encoding="utf-8")

        result = triage("t29d", str(export))

        self.assertEqual(result["count"], 2)
        text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("Standup at 9am", text)
        self.assertIn("Ship the release", text)

    def test_triage_max_40_lines(self) -> None:
        self._full_interview("t29e")
        export = Path(self._tmp) / "big.txt"
        export.write_text(
            "\n".join(f"message {i}" for i in range(60)),
            encoding="utf-8",
        )

        result = triage("t29e", str(export))

        self.assertEqual(result["count"], 60)
        text = Path(result["path"]).read_text(encoding="utf-8")
        # Only 40 numbered lines should appear.
        self.assertIn("40. message 39", text)
        self.assertNotIn("41. message 40", text)

    def test_triage_overwrites_on_second_call(self) -> None:
        self._full_interview("t29f")
        export = Path(self._tmp) / "chat.txt"
        export.write_text("First message\n", encoding="utf-8")

        triage("t29f", str(export))
        path = Path(self._tmp) / "work_products" / "t29f" / "team_inbox.md"
        text1 = path.read_text(encoding="utf-8")
        self.assertIn("First message", text1)

        export.write_text("Second message\n", encoding="utf-8")
        triage("t29f", str(export))
        text2 = path.read_text(encoding="utf-8")
        self.assertIn("Second message", text2)
        self.assertNotIn("First message", text2)

    def test_fastapi_team_inbox_200(self) -> None:
        self._full_interview("t29g")
        export = Path(self._tmp) / "api_chat.txt"
        export.write_text("Need the board pack tonight\n", encoding="utf-8")

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/team/inbox",
            json={"tenant_id": "t29g", "export_path": str(export)},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t29g")
        self.assertEqual(body["count"], 1)
        text = Path(body["path"]).read_text(encoding="utf-8")
        self.assertIn("board pack", text)

    def test_fastapi_team_inbox_400_without_profile(self) -> None:
        export = Path(self._tmp) / "no_profile.txt"
        export.write_text("hello\n", encoding="utf-8")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/team/inbox",
            json={"tenant_id": "no_profile_t29", "export_path": str(export)},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
