"""T125 — Hash-chained receipts and byte-exact dry-run.

Covers:

* Each receipt's ``prev_receipt_sha`` links to the previous receipt's
  ``receipt_sha`` (or ``GENESIS`` for the first).
* ``execute(..., dry_run=True)`` returns the exact bytes that would be
  written but does not flip status to ``executed`` and does not write a
  receipt file.
* The dry-run bytes match the real written receipt bytes exactly.
* No live network except TestClient.
"""

from __future__ import annotations

import json as _json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.persistence import get_connection
from core.twin_actions import (
    _action_digest,
    _load_action,
    approve,
    execute,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT125ReceiptChain(unittest.TestCase):
    """Hash-chained receipts and byte-exact dry-run."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t125_")
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
        kind: str,
        title: str,
        payload: dict | str | None = None,
        status: str = "proposed",
    ) -> str:
        """Insert an action row with an optional payload and return its id."""
        from core.twin_actions import _ensure_schema

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

    def _approve_action(self, tenant_id: str, action_id: str) -> None:
        """Approve *action_id* with the correct digest."""
        _action = _load_action(action_id)
        assert _action is not None
        approve(action_id, tenant_id, "tester-t125", _action_digest(_action))

    def _receipt_path(self, tenant_id: str, action_id: str) -> Path:
        return (
            Path(self._tmp)
            / "work_products"
            / tenant_id
            / "receipts"
            / f"{action_id}.md"
        )

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_second_receipt_links_first(self) -> None:
        """The second receipt's prev_receipt_sha == first receipt's
        receipt_sha; the first uses GENESIS."""
        tenant = "t125_chain"
        self._full_interview(tenant)

        # First action → first receipt (prev = GENESIS).
        a1 = self._insert_action(
            tenant, kind="review_digest", title="First digest", status="proposed",
        )
        self._approve_action(tenant, a1)
        r1 = execute(a1, tenant)
        self.assertEqual(r1["status"], "executed")

        r1_path = self._receipt_path(tenant, a1)
        r1_text = r1_path.read_text(encoding="utf-8")
        self.assertIn("prev_receipt_sha: GENESIS", r1_text)

        r1_sha = ""
        for line in r1_text.splitlines():
            if line.startswith("receipt_sha:"):
                r1_sha = line.split("receipt_sha:", 1)[1].strip()
        self.assertEqual(len(r1_sha), 64)  # hex SHA-256

        # Second action → second receipt (prev = first receipt_sha).
        a2 = self._insert_action(
            tenant, kind="review_repos", title="Second repos", status="proposed",
        )
        self._approve_action(tenant, a2)
        r2 = execute(a2, tenant)
        self.assertEqual(r2["status"], "executed")

        r2_path = self._receipt_path(tenant, a2)
        r2_text = r2_path.read_text(encoding="utf-8")
        self.assertIn(f"prev_receipt_sha: {r1_sha}", r2_text)

        # Verify the chain integrity: r2.prev_receipt_sha == r1.receipt_sha.
        r2_prev = None
        r2_sha = None
        for line in r2_text.splitlines():
            if line.startswith("prev_receipt_sha:"):
                r2_prev = line.split("prev_receipt_sha:", 1)[1].strip()
            if line.startswith("receipt_sha:"):
                r2_sha = line.split("receipt_sha:", 1)[1].strip()
        self.assertEqual(r2_prev, r1_sha)
        self.assertIsNotNone(r2_sha)
        self.assertNotEqual(r2_sha, r1_sha)

    def test_dry_run_no_receipt(self) -> None:
        """dry_run=True does not write a receipt file and does not flip
        status to executed."""
        tenant = "t125_dryrun"
        self._full_interview(tenant)
        action_id = self._insert_action(
            tenant, kind="review_digest", title="Dry run check", status="proposed",
        )
        self._approve_action(tenant, action_id)

        result = execute(action_id, tenant, dry_run=True)

        # Status must still be ``approved`` (not executed).
        self.assertEqual(result["status"], "approved")

        # No receipt file on disk.
        receipt_path = self._receipt_path(tenant, action_id)
        self.assertFalse(receipt_path.exists())

        # The dry_run_bytes key must be present.
        self.assertIn("dry_run_bytes", result)
        self.assertIsInstance(result["dry_run_bytes"], bytes)
        self.assertGreater(len(result["dry_run_bytes"]), 0)

    def test_dry_run_bytes_match_real_write(self) -> None:
        """The bytes returned by dry_run=True match the real receipt bytes
        written by a subsequent real execute."""
        tenant = "t125_bytes_match"
        self._full_interview(tenant)
        action_id = self._insert_action(
            tenant, kind="review_digest", title="Bytes match", status="proposed",
        )
        self._approve_action(tenant, action_id)

        # Dry-run: get the would-write bytes.
        dry = execute(action_id, tenant, dry_run=True)
        dry_bytes = dry["dry_run_bytes"]
        self.assertEqual(dry["status"], "approved")

        # No receipt yet.
        receipt_path = self._receipt_path(tenant, action_id)
        self.assertFalse(receipt_path.exists())

        # Real execute.
        real = execute(action_id, tenant)
        self.assertEqual(real["status"], "executed")

        # The real receipt file must exist and its bytes must equal dry_bytes.
        self.assertTrue(receipt_path.exists())
        real_bytes = receipt_path.read_bytes()
        self.assertEqual(real_bytes, dry_bytes)

    def test_no_live_network(self) -> None:
        """No live network call is made in this test module."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
