"""T48 — Resume includes profile name when present.

Covers:
- render_resume() writes the file even when profile has no name.
- When a name is present in the stored profile, the resume contains it.
- FastAPI resume route still returns 200.
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
from core.twin_resume_pack import render_resume
from fastapi.testclient import TestClient


class TestT48ResumeName(unittest.TestCase):
    """Resume-pack name inclusion."""

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

    def _inject_name(self, tenant_id: str, name: str) -> None:
        """Add a ``name`` field to the latest committed profile's layers JSON."""
        from core.persistence import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT profile_id, layers FROM twin_profiles "
                "WHERE tenant_id = ? ORDER BY version DESC LIMIT 1",
                (tenant_id,),
            ).fetchone()
            if row is None:
                raise AssertionError("no committed profile to inject name into")
            layers = json.loads(row["layers"])
            layers["name"] = name
            conn.execute(
                "UPDATE twin_profiles SET layers = ? WHERE profile_id = ?",
                (json.dumps(layers), row["profile_id"]),
            )

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_render_resume_writes_file_when_profile_has_no_name(self) -> None:
        """Without a name field the resume still renders and skips the line."""
        self._full_interview("t48a")

        result = render_resume("t48a")
        self.assertEqual(result["tenant_id"], "t48a")
        resume_path = Path(result["path"])
        self.assertTrue(resume_path.exists())

        text = resume_path.read_text(encoding="utf-8")
        # Name line should NOT appear when profile has no name.
        self.assertNotIn("**Name:**", text)
        # Role and Work Products should still be present.
        self.assertIn("**Role:**", text)
        self.assertIn("## Work Products", text)

    def test_render_resume_contains_name_when_present(self) -> None:
        """When the stored profile has a name, the resume includes it."""
        self._full_interview("t48b")
        self._inject_name("t48b", "Amin Azimi")

        result = render_resume("t48b")
        text = Path(result["path"]).read_text(encoding="utf-8")

        self.assertIn("**Name:** Amin Azimi", text)
        # Role must still be present.
        self.assertIn("**Role:**", text)

    def test_render_resume_does_not_invent_name_when_missing(self) -> None:
        """No name in profile means no **Name:** line at all — never invented."""
        self._full_interview("t48c")

        result = render_resume("t48c")
        text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertNotIn("**Name:**", text)

    def test_fastapi_resume_render_200(self) -> None:
        """FastAPI resume route still returns 200."""
        self._full_interview("t48d")

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/resume/render",
            json={"tenant_id": "t48d"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t48d")
        self.assertTrue(Path(body["path"]).exists())


if __name__ == "__main__":
    unittest.main()
