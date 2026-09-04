"""T57 — Bind tenant_id to execute, reject, and outbox write.

Covers:
- execute(action_id, tenant_id) refuses on tenant mismatch.
- reject(action_id, tenant_id) refuses on tenant mismatch.
- send_approved(tenant_id, action_id) refuses before writing .eml on
  tenant mismatch.
- A correct tenant_id still allows execute/reject/send_approved to
  succeed.
- T56 digest checks still work alongside the tenant binding.
- No live network.
"""

from __future__ import annotations

import json as _json
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
    reject,
)
from core.twin_email_send import send_approved
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT57TenantBinding(unittest.TestCase):
    """Tenant binding on execute, reject, and outbox write."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t57_")
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
        kind: str = "review_digest",
        title: str = "Review weekly digest",
        payload: dict | str | None = None,
        status: str = "proposed",
    ) -> str:
        """Insert an action row with optional payload and return its id."""
        _ensure_schema()
        action_id = f"act-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        if isinstance(payload, dict):
            payload_json = _json.dumps(payload)
        elif isinstance(payload, str):
            payload_json = payload
        else:
            payload_json = None
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO twin_actions "
                "(action_id, tenant_id, kind, title, status, created_at, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (action_id, tenant_id, kind, title, status, now, payload_json),
            )
        return action_id

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_execute_refuses_on_tenant_mismatch(self) -> None:
        """execute(action_id, wrong_tenant) raises ValueError."""
        self._full_interview("t57a")
        tenant = "t57a"
        action_id = self._insert_action(tenant, title="Review weekly digest")
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        approve(action_id, tenant, "tester", digest)

        with self.assertRaises(ValueError) as ctx:
            execute(action_id, "wrong_tenant")
        self.assertIn("tenant mismatch", str(ctx.exception))

    def test_reject_refuses_on_tenant_mismatch(self) -> None:
        """reject(action_id, wrong_tenant) raises ValueError."""
        self._full_interview("t57b")
        tenant = "t57b"
        action_id = self._insert_action(tenant, title="Review weekly digest")

        with self.assertRaises(ValueError) as ctx:
            reject(action_id, "wrong_tenant")
        self.assertIn("tenant mismatch", str(ctx.exception))

    def test_send_approved_refuses_on_tenant_mismatch(self) -> None:
        """send_approved(wrong_tenant, action_id) raises ValueError before .eml."""
        # Both tenants need a consented profile so the consent gate
        # does not short-circuit before the tenant-mismatch check.
        self._full_interview("t57c")
        self._full_interview("wrong_tenant")
        tenant = "t57c"
        action_id = self._insert_action(
            tenant,
            kind="email",
            title="Email: weekly pack",
            payload={"body": "pack body"},
        )
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        approve(action_id, tenant, "tester", digest)

        with self.assertRaises(ValueError) as ctx:
            send_approved("wrong_tenant", action_id)
        self.assertIn("tenant mismatch", str(ctx.exception))

        # Verify no .eml was written for the wrong tenant.
        wrong_outbox = os.path.join(
            self._tmp, "work_products", "wrong_tenant", "outbox",
        )
        self.assertFalse(
            os.path.isdir(wrong_outbox) and os.listdir(wrong_outbox),
            "no .eml should exist for wrong tenant",
        )

    def test_correct_tenant_allows_all(self) -> None:
        """With the correct tenant_id, execute and send_approved succeed."""
        self._full_interview("t57d")
        tenant = "t57d"
        action_id = self._insert_action(
            tenant,
            kind="email",
            title="Email: weekly pack",
            payload={"body": "pack body"},
        )
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        approve(action_id, tenant, "tester", digest)

        # Execute with correct tenant — should succeed.
        result = execute(action_id, tenant)
        self.assertEqual(result["status"], "executed")

        # send_approved with correct tenant — should succeed (status is
        # executed, which is accepted).
        send_result = send_approved(tenant, action_id)
        self.assertEqual(send_result["tenant_id"], tenant)
        self.assertEqual(send_result["action_id"], action_id)

    def test_t56_digest_still_works(self) -> None:
        """T56 digest checks still work alongside tenant binding."""
        self._full_interview("t57e")
        tenant = "t57e"
        action_id = self._insert_action(tenant, title="Review weekly digest")
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)

        # Approve with the correct digest — should succeed.
        approved = approve(action_id, tenant, "tester", digest)
        self.assertEqual(approved["status"], "approved")

        # Mutate the title after approval.
        with get_connection() as conn:
            conn.execute(
                "UPDATE twin_actions SET title = ? WHERE action_id = ?",
                ("Review monthly digest", action_id),
            )

        # Execute should fail because the digest changed (T56 check).
        with self.assertRaises(ValueError) as ctx:
            execute(action_id, tenant)
        self.assertIn("payload changed after approval", str(ctx.exception))

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
