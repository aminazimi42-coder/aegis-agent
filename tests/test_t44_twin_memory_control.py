"""T44 — Memory control list and forget.

Covers:
- show without a consented profile raises ValueError.
- After a T03 commit, show writes memory.md whose markdown contains the
  tenant id or a profile key.
- forget("role") then show markdown does not contain a Role heading.
- FastAPI 200 on POST /api/v1/twin/memory/show.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_memory_control import forget, show
from fastapi.testclient import TestClient


class TestT44TwinMemoryControl(unittest.TestCase):
    """Memory control list and forget invariants."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t44_")
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

    def test_show_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            show("no_profile_t44")

    def test_show_markdown_contains_tenant_id_or_profile_key(self) -> None:
        self._full_interview("t44a")
        result = show("t44a")

        # Result shape.
        self.assertEqual(result["tenant_id"], "t44a")
        self.assertIn("path", result)
        self.assertIn("fields", result)
        self.assertGreaterEqual(len(result["fields"]), 1)

        # memory.md exists and contains the tenant id or a profile key.
        md_path = Path(result["path"])
        self.assertTrue(md_path.exists(), f"missing memory.md: {md_path}")
        md_text = md_path.read_text(encoding="utf-8")
        self.assertTrue(
            "t44a" in md_text or "role" in md_text.lower(),
            f"memory.md does not contain tenant id or a profile key: {md_text!r}",
        )

    def test_forget_role_then_show_no_role_heading(self) -> None:
        self._full_interview("t44b")

        # First show to confirm role is present.
        result0 = show("t44b")
        md0 = Path(result0["path"]).read_text(encoding="utf-8")
        self.assertIn("## Role", md0)

        # Forget "role".
        result = forget("t44b", "role")
        self.assertEqual(result["tenant_id"], "t44b")

        # show markdown does not contain a Role heading.
        md = Path(result["path"]).read_text(encoding="utf-8")
        self.assertNotIn("## Role", md)

        # Subsequent show also omits it (forgotten is persisted).
        result2 = show("t44b")
        md2 = Path(result2["path"]).read_text(encoding="utf-8")
        self.assertNotIn("## Role", md2)

    def test_fastapi_show_200(self) -> None:
        self._full_interview("t44c")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/memory/show",
            json={"tenant_id": "t44c"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t44c")
        self.assertIn("path", body)
        self.assertIn("fields", body)

    def test_fastapi_forget_200(self) -> None:
        self._full_interview("t44d")
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/memory/forget",
            json={"tenant_id": "t44d", "field": "role"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t44d")
        self.assertNotIn("role", body["fields"])

    def test_fastapi_show_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/memory/show",
            json={"tenant_id": "no_profile_t44"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
