"""T19 — Local email triage drafts without sending mail.

Covers:
- triage without a consented profile raises ValueError.
- triage with a non-existent mail dir raises ValueError.
- After a T03-style commit + one .eml file (From: a@b.com, Subject: Budget review):
  triage file exists, contains "Budget review" and "Draft".
- Dedup: second triage of the same .eml ingested == 0.
- FastAPI 200 on POST /api/v1/twin/email/triage.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_email_triage import triage
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT19TwinEmailTriage(unittest.TestCase):
    """Local email triage invariants."""

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

    def _write_eml(self, path: Path, sender: str, subject: str) -> None:
        """Write a minimal .eml file."""
        path.write_text(
            f"From: {sender}\n"
            f"Subject: {subject}\n"
            f"Content-Type: text/plain; charset=utf-8\n"
            f"\n"
            f"Hello, please review the budget.\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_triage_without_profile_raises_value_error(self) -> None:
        mail_dir = Path(self._tmp) / "mail"
        mail_dir.mkdir()
        with self.assertRaises(ValueError):
            triage("no_profile_t19", str(mail_dir))

    def test_triage_missing_dir_raises_value_error(self) -> None:
        self._full_interview("t19b")
        with self.assertRaises(ValueError):
            triage("t19b", str(Path(self._tmp) / "nonexistent"))

    def test_triage_creates_file_with_budget_review_and_draft(self) -> None:
        self._full_interview("t19a")
        mail_dir = Path(self._tmp) / "mail_t19a"
        mail_dir.mkdir()
        self._write_eml(mail_dir / "msg.eml", "a@b.com", "Budget review")

        result = triage("t19a", str(mail_dir))

        self.assertEqual(result["tenant_id"], "t19a")
        self.assertGreaterEqual(result["ingested"], 1)

        triage_path = Path(result["path"])
        self.assertTrue(triage_path.exists(), f"missing file: {triage_path}")

        text = triage_path.read_text(encoding="utf-8")
        self.assertIn("Budget review", text)
        self.assertIn("Draft", text)

    def test_triage_dedup_second_call(self) -> None:
        self._full_interview("t19c")
        mail_dir = Path(self._tmp) / "mail_t19c"
        mail_dir.mkdir()
        self._write_eml(mail_dir / "msg.eml", "a@b.com", "Budget review")

        result1 = triage("t19c", str(mail_dir))
        self.assertGreaterEqual(result1["ingested"], 1)

        result2 = triage("t19c", str(mail_dir))
        self.assertEqual(result2["ingested"], 0)

    def test_fastapi_triage_200(self) -> None:
        self._full_interview("t19d")
        mail_dir = Path(self._tmp) / "mail_t19d"
        mail_dir.mkdir()
        self._write_eml(mail_dir / "msg.eml", "a@b.com", "Budget review")

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/email/triage",
            json={"tenant_id": "t19d", "mail_dir": str(mail_dir)},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t19d")
        self.assertGreaterEqual(body["ingested"], 1)

    def test_fastapi_triage_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/email/triage",
            json={"tenant_id": "no_profile_t19", "mail_dir": "/tmp"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
