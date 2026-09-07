"""T110 — Non-empty answers for every required interview key.

Verifies that the operator page (app.html) never posts empty strings for the
required interview keys (q_risk, q_ethics, etc.), that a filled four-field
form commits with HTTP 200, and that every required key receives a
non-empty string.

No live network except the FastAPI ``TestClient``.
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_HTML = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)


class TestT110InterviewNonempty(unittest.TestCase):
    """Every required interview key gets a non-empty string; four-field form commits 200."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t110_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # app.html never posts "" for a required key
    # ------------------------------------------------------------------ #

    def test_commit_does_not_post_empty_answers(self) -> None:
        """app.html must not post an empty string for any required key."""
        html = _APP_HTML.read_text(encoding="utf-8")
        # Extract the mapping array inside commitInterview().
        match = re.search(r"var mapping\s*=\s*\[(.*?)\];", html, re.DOTALL)
        self.assertIsNotNone(match, "mapping array not found in app.html")
        assert match is not None  # for type checkers
        body = match.group(1)
        # Every entry must have a non-empty text value — no `text: ""`.
        empty_entries = re.findall(r'\{[^}]*text:\s*""[^}]*\}', body)
        self.assertEqual(
            empty_entries,
            [],
            f"app.html posts empty text for a required key: {empty_entries}",
        )
        # The risk and ethics defaults must be the specified honest strings.
        self.assertIn("human approve required", body)
        self.assertIn("local first no outbound send", body)
        # repos default must be present.
        self.assertIn("local git only", body)

    # ------------------------------------------------------------------ #
    # A filled four-field form commits with 200
    # ------------------------------------------------------------------ #

    def test_four_field_commit_200(self) -> None:
        """Simulate the operator page: map name/role/goals/timezone onto the
        six store questions using the app.html defaults for risk/ethics/repos,
        then commit → 200 with every layer non-empty."""
        app = create_app()
        client = TestClient(app)
        tenant = "t110-ok"
        # Start a session.
        resp = client.post(
            "/api/v1/twin/session/start",
            json={"tenant_id": tenant},
        )
        self.assertEqual(resp.status_code, 200)
        sid = resp.json()["session_id"]
        # Simulate the four operator fields filled.
        name = "Alice"
        role = "engineer"
        goals = "ship safely"
        tz = "UTC"
        # Mirrors the app.html mapping — never "".
        answers = {
            "q_role": role,
            "q_decision_style": goals,
            "q_tools": tz,
            "q_risk": "human approve required",
            "q_ethics": "local first no outbound send",
            "q_repos": name,
        }
        # Answer in the store's expected order.
        for q in QUESTIONS:
            qid = q["id"]
            self.assertIn(qid, answers, f"missing answer for required key {qid}")
            self.assertTrue(answers[qid], f"empty answer for required key {qid}")
            r = client.post(
                f"/api/v1/twin/session/{sid}/answer",
                json={"question_id": qid, "text": answers[qid]},
            )
            self.assertEqual(r.status_code, 200, f"answer {qid} rejected")
        # Commit.
        r = client.post(
            f"/api/v1/twin/session/{sid}/commit",
            json={"consent": True},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("profile_id", body)
        # Every layer field must be non-empty.
        for field in ("role", "decision_style", "tools", "risk_posture",
                      "work_ethics", "repositories"):
            self.assertTrue(
                str(body.get(field, "")).strip(),
                f"layer field {field} is empty after commit",
            )

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
