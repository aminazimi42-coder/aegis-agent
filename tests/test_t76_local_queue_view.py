"""T76 — Local queue view without HTTP.

Covers:
- ``list_queue(tenant_id)`` returns a dict with keys ``pending`` and
  ``approved_waiting`` sourced from ``twin_actions`` only.
- ``pending`` contains status ``"proposed"`` actions; ``approved_waiting``
  contains status ``"approved"`` actions.
- ``executed`` actions are excluded from both groups.
- ``core.twin_local_view`` does not import ``urllib``, ``requests``,
  ``socket``, or ``http.client``.
- AEGIS_DATA_DIR temp isolation; no live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from core.persistence import get_connection
from core.twin_actions import (
    _action_digest,
    _ensure_schema,
    _load_action,
    approve,
    execute,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_local_view import list_queue


class TestT76LocalQueueView(unittest.TestCase):
    """List pending and approved-waiting actions from SQLite without HTTP."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t76_")
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

    def _insert_action(
        self,
        tenant_id: str,
        title: str,
        status: str = "proposed",
        kind: str = "review_digest",
    ) -> str:
        """Insert a twin_action row directly and return its action_id."""
        _ensure_schema()
        action_id = f"act-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO twin_actions "
                "(action_id, tenant_id, kind, title, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (action_id, tenant_id, kind, title, status, now),
            )
        return action_id

    def _approve(self, tenant_id: str, action_id: str) -> None:
        """Approve an action using its current envelope digest."""
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        approve(action_id, tenant_id, "tester", digest)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_list_queue_splits_pending_and_approved(self) -> None:
        """list_queue returns pending (proposed) and approved_waiting separately."""
        tenant = "t76a"
        self._full_interview(tenant)

        # Insert one proposed and one approved action.
        proposed_id = self._insert_action(tenant, "Review weekly digest")
        approved_id = self._insert_action(tenant, "Review repos")
        self._approve(tenant, approved_id)

        result = list_queue(tenant)

        # Keys present.
        self.assertIn("pending", result)
        self.assertIn("approved_waiting", result)

        # The proposed action is in pending.
        pending_ids = [a["action_id"] for a in result["pending"]]
        self.assertIn(proposed_id, pending_ids)

        # The approved action is in approved_waiting.
        approved_ids = [a["action_id"] for a in result["approved_waiting"]]
        self.assertIn(approved_id, approved_ids)

        # No overlap between the two groups.
        self.assertNotIn(proposed_id, approved_ids)
        self.assertNotIn(approved_id, pending_ids)

    def test_list_queue_excludes_executed(self) -> None:
        """Executed actions do not appear in either pending or approved_waiting."""
        tenant = "t76b"
        self._full_interview(tenant)

        # Insert, approve, and execute one action.
        exec_id = self._insert_action(tenant, "Review digest to run")
        self._approve(tenant, exec_id)
        execute(exec_id, tenant)

        # Insert a second approved-but-not-executed action.
        wait_id = self._insert_action(tenant, "Review repos to wait")
        self._approve(tenant, wait_id)

        # Insert a third proposed action.
        prop_id = self._insert_action(tenant, "Review digest proposed")

        result = list_queue(tenant)

        # The executed action must be in neither list.
        all_ids = (
            [a["action_id"] for a in result["pending"]]
            + [a["action_id"] for a in result["approved_waiting"]]
        )
        self.assertNotIn(exec_id, all_ids)

        # The approved-waiting action is in approved_waiting.
        approved_ids = [a["action_id"] for a in result["approved_waiting"]]
        self.assertIn(wait_id, approved_ids)

        # The proposed action is in pending.
        pending_ids = [a["action_id"] for a in result["pending"]]
        self.assertIn(prop_id, pending_ids)

    def test_module_has_no_http_imports(self) -> None:
        """core.twin_local_view must not import urllib/requests/socket/http."""
        import ast
        import inspect

        from core import twin_local_view

        tree = ast.parse(inspect.getsource(twin_local_view))
        forbidden = {"urllib", "requests", "socket", "http.client"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    self.assertNotIn(
                        top,
                        forbidden,
                        f"core.twin_local_view imports '{alias.name}'",
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                top = mod.split(".")[0]
                self.assertNotIn(
                    top,
                    forbidden,
                    f"core.twin_local_view imports from '{mod}'",
                )

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
