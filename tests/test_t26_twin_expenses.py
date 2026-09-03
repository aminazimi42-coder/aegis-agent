"""T26 — Expense notes from local receipt texts.

Covers:
- ingest_receipts() without a consented profile raises ValueError.
- After a T03 commit, writing a receipt "Hotel\\n$210.00":
  expenses.md contains Hotel, 210, and "Do not pay".
- FastAPI 200 on POST /api/v1/twin/expenses/ingest.
- No live network / no paid LLM required.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_expenses import ingest_receipts
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT26TwinExpenses(unittest.TestCase):
    """Expense- ingest invariants."""

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

    def _write_receipts(self, receipts: dict[str, str]) -> str:
        """Write receipt .txt files into a temp subdir and return its path."""
        rdir = Path(self._tmp) / "receipts"
        rdir.mkdir()
        for name, content in receipts.items():
            (rdir / name).write_text(content, encoding="utf-8")
        return str(rdir)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_ingest_without_profile_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            ingest_receipts("no_profile_t26", "/tmp")

    def test_ingest_with_nonexistent_dir_raises_value_error(self) -> None:
        self._full_interview("t26b")
        with self.assertRaises(ValueError):
            ingest_receipts("t26b", "/nonexistent/dir/does/not/exist")

    def test_ingest_writes_expenses_md_with_vendor_amount_and_safety(self) -> None:
        self._full_interview("t26a")
        rdir = self._write_receipts({"hotel.txt": "Hotel\n$210.00\n"})

        result = ingest_receipts("t26a", rdir)

        self.assertEqual(result["tenant_id"], "t26a")
        self.assertEqual(result["count"], 1)

        expenses_path = (
            Path(self._tmp) / "work_products" / "t26a" / "expenses.md"
        )
        self.assertTrue(expenses_path.exists())
        text = expenses_path.read_text(encoding="utf-8")
        self.assertIn("Hotel", text)
        self.assertIn("210", text)
        self.assertIn("Do not pay without written approval.", text)

    def test_ingest_parses_amount_without_dollar_sign(self) -> None:
        self._full_interview("t26c")
        rdir = self._write_receipts({"lunch.txt": "Cafe\n123.45\n"})

        ingest_receipts("t26c", rdir)

        expenses_path = (
            Path(self._tmp) / "work_products" / "t26c" / "expenses.md"
        )
        text = expenses_path.read_text(encoding="utf-8")
        self.assertIn("123.45", text)

    def test_ingest_unparsed_amount(self) -> None:
        self._full_interview("t26d")
        rdir = self._write_receipts({"misc.txt": "Misc Vendor\nno amount here\n"})

        ingest_receipts("t26d", rdir)

        expenses_path = (
            Path(self._tmp) / "work_products" / "t26d" / "expenses.md"
        )
        text = expenses_path.read_text(encoding="utf-8")
        self.assertIn("unparsed", text)

    def test_ingest_overwrites_on_second_call(self) -> None:
        self._full_interview("t26e")
        rdir = self._write_receipts({"a.txt": "Alpha\n$100.00\n"})
        ingest_receipts("t26e", rdir)
        expenses_path = (
            Path(self._tmp) / "work_products" / "t26e" / "expenses.md"
        )
        text1 = expenses_path.read_text(encoding="utf-8")
        self.assertIn("Alpha", text1)

        # Overwrite the receipt with a different vendor.
        Path(rdir, "a.txt").write_text("Beta\n$200.00\n", encoding="utf-8")
        ingest_receipts("t26e", rdir)
        text2 = expenses_path.read_text(encoding="utf-8")
        self.assertIn("Beta", text2)
        self.assertNotIn("Alpha", text2)

    def test_ingest_multiple_receipts(self) -> None:
        self._full_interview("t26f")
        rdir = self._write_receipts(
            {
                "a.txt": "Alpha\n$100.00\n",
                "b.txt": "Beta\n$200.00\n",
            }
        )
        result = ingest_receipts("t26f", rdir)
        self.assertEqual(result["count"], 2)
        expenses_path = (
            Path(self._tmp) / "work_products" / "t26f" / "expenses.md"
        )
        text = expenses_path.read_text(encoding="utf-8")
        self.assertIn("Alpha", text)
        self.assertIn("Beta", text)

    def test_fastapi_post_200(self) -> None:
        self._full_interview("t26g")
        rdir = self._write_receipts({"hotel.txt": "Hotel\n$210.00\n"})

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/expenses/ingest",
            json={"tenant_id": "t26g", "receipts_dir": rdir},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], "t26g")
        self.assertEqual(body["count"], 1)

    def test_fastapi_post_400_without_profile(self) -> None:
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/expenses/ingest",
            json={
                "tenant_id": "no_profile_t26",
                "receipts_dir": "/tmp",
            },
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
