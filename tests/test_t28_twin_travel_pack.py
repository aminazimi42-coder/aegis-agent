"""T28 — Travel pack from calendar events and local docs.

Covers:
- render_pack() without a consented profile raises ValueError.
- After a T03 commit + ingest calendar "Flight to Berlin":
  travel_pack.md contains "Flight to Berlin" and the written-approval line.
- FastAPI 200 on POST /api/v1/twin/travel/render.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_events import ingest_event
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_travel_pack import render_pack
from fastapi.testclient import TestClient


class TestT28TwinTravelPack(unittest.TestCase):
    """Travel-pack invariants."""

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

    def test_render_pack_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            render_pack("no_profile_t28")

    def test_render_pack_writes_flight_and_approval(self) -> None:
        self._full_interview("t28a")
        ingest_event(
            tenant_id="t28a",
            source="calendar",
            kind="meeting",
            payload={"summary": "Flight to Berlin", "start": "20260915T080000Z"},
        )

        result = render_pack("t28a")

        self.assertEqual(result["tenant_id"], "t28a")
        pack_path = Path(result["path"])
        self.assertTrue(pack_path.exists())

        text = pack_path.read_text(encoding="utf-8")
        self.assertIn("Flight to Berlin", text)
        self.assertIn("Do not book or pay without written approval.", text)

    def test_render_pack_lists_docs(self) -> None:
        self._full_interview("t28b")
        docs_dir = Path(self._tmp) / "docs"
        docs_dir.mkdir()
        (docs_dir / "ticket.pdf").write_text("x", encoding="utf-8")
        (docs_dir / "notes.txt").write_text("y", encoding="utf-8")
        (docs_dir / "plan.md").write_text("z", encoding="utf-8")
        (docs_dir / "ignore.csv").write_text("w", encoding="utf-8")

        result = render_pack("t28b", docs_dir=str(docs_dir))
        text = Path(result["path"]).read_text(encoding="utf-8")

        self.assertIn("ticket.pdf", text)
        self.assertIn("notes.txt", text)
        self.assertIn("plan.md", text)
        self.assertNotIn("ignore.csv", text)

    def test_render_pack_overwrites_on_second_call(self) -> None:
        self._full_interview("t28c")
        ingest_event(
            tenant_id="t28c",
            source="calendar",
            kind="meeting",
            payload={"summary": "Hotel in Paris", "start": "20260920T100000Z"},
        )

        render_pack("t28c")
        path = (
            Path(self._tmp) / "work_products" / "t28c" / "travel_pack.md"
        )
        text1 = path.read_text(encoding="utf-8")
        self.assertIn("Hotel in Paris", text1)

        # Second call with a new meeting should still produce a valid file.
        render_pack("t28c")
        text2 = path.read_text(encoding="utf-8")
        self.assertIn("Hotel in Paris", text2)

    def test_fastapi_travel_render_200(self) -> None:
        self._full_interview("t28d")
        ingest_event(
            tenant_id="t28d",
            source="calendar",
            kind="meeting",
            payload={"summary": "Flight to Tokyo", "start": "20261001T060000Z"},
        )

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/travel/render",
            json={"tenant_id": "t28d"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t28d")
        text = Path(body["path"]).read_text(encoding="utf-8")
        self.assertIn("Flight to Tokyo", text)
        self.assertIn("Do not book or pay without written approval.", text)

    def test_fastapi_travel_render_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/travel/render",
            json={"tenant_id": "no_profile_t28"},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
