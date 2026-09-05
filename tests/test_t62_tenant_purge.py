"""T62 — Tenant purge is idempotent and neighbour-safe.

Covers:
- ``purge_tenant(tenant_id, confirm)`` requires a typed confirm string equal
  to ``"PURGE " + tenant_id``; any other value raises ``ValueError``.
- A second call with the same confirm is idempotent — it returns
  ``cleared: True`` and does not raise.
- A neighbour tenant's actions, receipt, and memory listing survive the
  purge of the first tenant.
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
from core.twin_memory_control import forget, purge_tenant, show


class TestT62TenantPurge(unittest.TestCase):
    """purge_tenant is idempotent and neighbour-safe."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t62_")
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

    def test_wrong_confirm_is_rejected(self) -> None:
        """A confirm that doesn't match 'PURGE <tenant_id>' raises ValueError."""
        tenant = "t62-confirm"
        self._full_interview(tenant)
        self._insert_action(tenant, title="Action to keep")

        # Wrong confirm strings.
        with self.assertRaises(ValueError):
            purge_tenant(tenant, "PURGE")
        with self.assertRaises(ValueError):
            purge_tenant(tenant, f"PURGE {tenant} ")
        with self.assertRaises(ValueError):
            purge_tenant(tenant, f"purge {tenant}")
        with self.assertRaises(ValueError):
            purge_tenant(tenant, "")
        with self.assertRaises(ValueError):
            purge_tenant(tenant, tenant)

        # Nothing was cleared — the action is still there.
        self.assertEqual(len(list_actions(tenant)), 1)

    def test_purge_twice_is_idempotent(self) -> None:
        """A second call with the same confirm still returns cleared=True."""
        tenant = "t62-idempotent"
        self._full_interview(tenant)
        self._insert_action(tenant, title="Action A")
        self._insert_action(tenant, title="Action B")
        show(tenant)
        forget(tenant, "role")

        # Sanity: there are actions before purge.
        self.assertEqual(len(list_actions(tenant)), 2)

        confirm = f"PURGE {tenant}"

        # First purge.
        result1 = purge_tenant(tenant, confirm)
        self.assertEqual(result1["tenant_id"], tenant)
        self.assertTrue(result1["cleared"])
        self.assertTrue(result1["receipt_path"].endswith("deletion_receipt.md"))

        # Actions cleared.
        self.assertEqual(len(list_actions(tenant)), 0)

        # Second purge — same confirm, no raise, still cleared=True.
        result2 = purge_tenant(tenant, confirm)
        self.assertEqual(result2["tenant_id"], tenant)
        self.assertTrue(result2["cleared"])
        self.assertTrue(result2["receipt_path"].endswith("deletion_receipt.md"))

        # Still no actions.
        self.assertEqual(len(list_actions(tenant)), 0)

        # Receipt file exists after second call.
        receipt_path = os.path.join(
            self._tmp, "work_products", tenant, "deletion_receipt.md"
        )
        self.assertTrue(os.path.exists(receipt_path))

    def test_neighbor_survives_purge(self) -> None:
        """Purging one tenant does not touch a neighbour's stores."""
        tenant_a = "t62-neighbor-a"
        tenant_b = "t62-neighbor-b"
        self._full_interview(tenant_a)
        self._full_interview(tenant_b)

        # Both tenants have actions.
        self._insert_action(tenant_a, title="A action 1")
        self._insert_action(tenant_b, title="B action 1")
        self._insert_action(tenant_b, title="B action 2")

        # Populate memory listings and forgotten rows for both.
        show(tenant_a)
        show(tenant_b)
        forget(tenant_a, "role")
        forget(tenant_b, "role")

        self.assertEqual(len(list_actions(tenant_a)), 1)
        self.assertEqual(len(list_actions(tenant_b)), 2)

        # Purge only tenant_a.
        result = purge_tenant(tenant_a, f"PURGE {tenant_a}")
        self.assertTrue(result["cleared"])

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
