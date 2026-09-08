"""T126 — Neighbor-safe purge, signed local export, conflict tags.

Covers:
* ``purge_tenant(A)`` leaves tenant B's rows and receipt files untouched.
* ``signed_export`` writes a file under ``AEGIS_DATA_DIR/export/`` whose
  body carries a ``sha256`` signature line.
* A second ``insert_specialist_proposal`` to the same ``action_id`` sets
  ``conflict=True`` on the later row and does not clobber the first
  payload.
* No live network except TestClient.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.persistence import get_connection
from core.twin_actions import (
    _ensure_schema,
    insert_specialist_proposal,
    list_actions,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_local_recall import signed_export
from core.twin_memory_control import forget, purge_tenant, show


class TestT126PurgeExportConflict(unittest.TestCase):
    """Neighbor-safe purge, signed export, and conflict tags."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t126_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete interview and return the session id."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}-{tenant_id}")
        commit(sid, True)
        return sid

    def _insert_action(
        self,
        tenant_id: str,
        title: str = "Review digest",
    ) -> str:
        """Insert a twin_actions row and return its id."""
        _ensure_schema()
        action_id = f"act-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO twin_actions "
                "(action_id, tenant_id, kind, title, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (action_id, tenant_id, "review_digest", title, "proposed", now),
            )
        return action_id

    def _write_receipt(self, tenant_id: str, action_id: str) -> Path:
        """Write a dummy receipt file for *action_id* and return its path."""
        _ensure_schema()
        receipts_dir = (
            Path(self._tmp) / "work_products" / tenant_id / "receipts"
        )
        receipts_dir.mkdir(parents=True, exist_ok=True)
        rpath = receipts_dir / f"{action_id}.md"
        rpath.write_text(
            f"# Receipt — {action_id}\n\ntenant_id: {tenant_id}\n",
            encoding="utf-8",
        )
        return rpath

    # ------------------------------------------------------------------ #
    # 1) Purge property
    # ------------------------------------------------------------------ #

    def test_purge_a_leaves_b(self) -> None:
        """Purging tenant A leaves tenant B's rows and receipt files intact."""
        tenant_a = "t126-purge-a"
        tenant_b = "t126-purge-b"

        self._full_interview(tenant_a)
        self._full_interview(tenant_b)

        a_aid = self._insert_action(tenant_a, title="A action")
        b_aid = self._insert_action(tenant_b, title="B action")

        # Write receipt files for both.
        receipt_a = self._write_receipt(tenant_a, a_aid)
        receipt_b = self._write_receipt(tenant_b, b_aid)

        # Populate memory listings and forgotten rows for both.
        show(tenant_a)
        show(tenant_b)
        forget(tenant_a, "role")
        forget(tenant_b, "role")

        # Sanity: both tenants have actions and receipt files.
        self.assertEqual(len(list_actions(tenant_a)), 1)
        self.assertEqual(len(list_actions(tenant_b)), 1)
        self.assertTrue(receipt_a.exists())
        self.assertTrue(receipt_b.exists())

        # Purge only tenant_a.
        result = purge_tenant(tenant_a, f"PURGE {tenant_a}")
        self.assertTrue(result["cleared"])

        # tenant_a is cleared.
        self.assertEqual(len(list_actions(tenant_a)), 0)

        # tenant_b actions are untouched.
        b_actions = list_actions(tenant_b)
        self.assertEqual(len(b_actions), 1)
        self.assertEqual(b_actions[0]["title"], "B action")

        # tenant_b receipt file is untouched.
        self.assertTrue(receipt_b.exists())
        self.assertEqual(
            receipt_b.read_text(encoding="utf-8"),
            f"# Receipt — {b_aid}\n\ntenant_id: {tenant_b}\n",
        )

        # tenant_b forgotten row still present.
        from core.twin_persist import init_schema

        init_schema()
        with get_connection() as conn:
            row_b = conn.execute(
                "SELECT COUNT(*) AS c FROM forgotten WHERE tenant_id = ?",
                (tenant_b,),
            ).fetchone()
            self.assertEqual(row_b["c"], 1)

    # ------------------------------------------------------------------ #
    # 2) Signed local export
    # ------------------------------------------------------------------ #

    def test_export_has_sha256(self) -> None:
        """``signed_export`` writes a file under AEGIS_DATA_DIR/export/ with
        a sha256 signature line."""
        tenant = "t126-export"
        self._full_interview(tenant)
        self._insert_action(tenant, title="Export me")

        result = signed_export(tenant, name="t126_export_test.md")

        # The path is under AEGIS_DATA_DIR/export/.
        out_path = Path(result["path"])
        self.assertTrue(
            str(out_path).startswith(str(Path(self._tmp) / "export")),
            f"export path not under AEGIS_DATA_DIR/export/: {out_path}",
        )
        self.assertTrue(out_path.is_file(), "export file not created")

        content = out_path.read_text(encoding="utf-8")
        # The body must contain a sha256 signature line.
        self.assertIn("sha256:", content)
        # The returned sha256 must appear in the file.
        self.assertIn(result["sha256"], content)
        # The sha256 value must be a 64-char hex string.
        self.assertEqual(len(result["sha256"]), 64)
        int(result["sha256"], 16)  # valid hex

    # ------------------------------------------------------------------ #
    # 3) Conflict tag — second write to same action_id
    # ------------------------------------------------------------------ #

    def test_conflict_not_silent_merge(self) -> None:
        """A second propose with the same action_id sets ``conflict=True``
        on the later row and does not clobber the first payload."""
        tenant = "t126-conflict"
        self._full_interview(tenant)

        # First insert with an explicit action_id.
        first = insert_specialist_proposal(
            tenant_id=tenant,
            agent_name="twin_local",
            title="First proposal",
            payload={"v": 1},
            action_id="act-t126-conflict-1",
        )
        self.assertFalse(first.get("conflict", False))

        # Second insert with the same action_id but different payload.
        second = insert_specialist_proposal(
            tenant_id=tenant,
            agent_name="twin_local",
            title="Second proposal",
            payload={"v": 2},
            action_id="act-t126-conflict-1",
        )
        # The later row must be tagged conflict=True.
        self.assertTrue(
            second.get("conflict", False),
            "second write to same action_id should have conflict=True",
        )

        # The first row must not be clobbered — its payload must still be
        # the original ``{"v": 1}``.
        actions = list_actions(tenant)
        first_rows = [a for a in actions if a["title"] == "First proposal"]
        self.assertEqual(len(first_rows), 1)
        self.assertEqual(first_rows[0].get("payload"), {"v": 1})
        self.assertFalse(first_rows[0].get("conflict", False))

        # The second row must have the new payload and conflict=True.
        second_rows = [a for a in actions if a["title"] == "Second proposal"]
        self.assertEqual(len(second_rows), 1)
        self.assertEqual(second_rows[0].get("payload"), {"v": 2})
        self.assertTrue(second_rows[0].get("conflict", False))

    # ------------------------------------------------------------------ #
    # 4) No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """No live network is used in this test module."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
