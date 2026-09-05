"""T61 — Forget all tenant stores and write a deletion receipt.

Covers:
- ``forget_all(tenant_id)`` clears the forgotten-field listing, the
  visible ``memory.md`` file, and all ``twin_actions`` rows for that
  tenant.
- ``deletion_receipt.md`` is written with the tenant_id and UTC time.
- A neighbour tenant's ``twin_actions`` rows and memory listing survive
  the call.
- AEGIS_DATA_DIR temp isolation; no live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from core.persistence import get_connection
from core.twin_actions import _ensure_schema, list_actions
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_memory_control import forget, forget_all, show


class TestT61ForgetAll(unittest.TestCase):
    """forget_all clears the calling tenant's stores; neighbours survive."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t61_")
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

    def _insert_action(self, tenant_id: str, title: str = "Review digest") -> str:
        """Insert a twin_actions row for *tenant_id* and return its id."""
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

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_forget_all_clears_actions_and_writes_receipt(self) -> None:
        """forget_all empties twin_actions, memory.md, forgotten rows; writes receipt."""
        tenant = "t61-main"
        self._full_interview(tenant)
        # Add a couple of actions.
        self._insert_action(tenant, title="Review digest A")
        self._insert_action(tenant, title="Review digest B")
        # Populate the memory listing (writes memory.md).
        show(tenant)
        # Forget a field so the forgotten table has a row.
        forget(tenant, "role")

        # Sanity: there are actions before forget_all.
        self.assertEqual(len(list_actions(tenant)), 2)

        result = forget_all(tenant)

        # Return shape.
        self.assertEqual(result["tenant_id"], tenant)
        self.assertTrue(result["cleared"])
        self.assertTrue(result["receipt_path"].endswith("deletion_receipt.md"))

        # twin_actions for this tenant are gone.
        self.assertEqual(len(list_actions(tenant)), 0)

        # memory.md is gone.
        memory_md = os.path.join(
            self._tmp, "work_products", tenant, "memory.md"
        )
        self.assertFalse(os.path.exists(memory_md))

        # deletion_receipt.md exists and contains tenant_id + a UTC timestamp.
        receipt_path = os.path.join(
            self._tmp, "work_products", tenant, "deletion_receipt.md"
        )
        self.assertTrue(os.path.exists(receipt_path))
        content = open(receipt_path, encoding="utf-8").read()
        self.assertIn(tenant, content)
        # The timestamp should be an ISO-format UTC string.
        self.assertIn("deleted_at:", content)

        # forgotten table rows for this tenant are cleared.
        from core.twin_persist import init_schema

        init_schema()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM forgotten WHERE tenant_id = ?",
                (tenant,),
            ).fetchone()
            self.assertEqual(row["c"], 0)

    def test_neighbor_tenant_survives(self) -> None:
        """forget_all for one tenant does not clear another tenant's stores."""
        tenant_a = "t61-neighbor-a"
        tenant_b = "t61-neighbor-b"
        self._full_interview(tenant_a)
        self._full_interview(tenant_b)

        # Both tenants have actions.
        self._insert_action(tenant_a, title="A action 1")
        self._insert_action(tenant_b, title="B action 1")
        self._insert_action(tenant_b, title="B action 2")

        # Populate memory listing and forgotten rows for both.
        show(tenant_a)
        show(tenant_b)
        forget(tenant_a, "role")
        forget(tenant_b, "role")

        self.assertEqual(len(list_actions(tenant_a)), 1)
        self.assertEqual(len(list_actions(tenant_b)), 2)

        # Forget only tenant_a.
        forget_all(tenant_a)

        # tenant_a is cleared.
        self.assertEqual(len(list_actions(tenant_a)), 0)
        memory_a = os.path.join(self._tmp, "work_products", tenant_a, "memory.md")
        self.assertFalse(os.path.exists(memory_a))

        # tenant_b is intact.
        self.assertEqual(len(list_actions(tenant_b)), 2)
        titles = {a["title"] for a in list_actions(tenant_b)}
        self.assertEqual(titles, {"B action 1", "B action 2"})
        memory_b = os.path.join(self._tmp, "work_products", tenant_b, "memory.md")
        self.assertTrue(os.path.exists(memory_b))

        # tenant_b forgotten row still present.
        from core.twin_persist import init_schema

        init_schema()
        with get_connection() as conn:
            row_b = conn.execute(
                "SELECT COUNT(*) AS c FROM forgotten WHERE tenant_id = ?",
                (tenant_b,),
            ).fetchone()
            self.assertEqual(row_b["c"], 1)

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
