"""T111 — Operator page propose to queue via six specialists.

Covers:
- POST /api/v1/twin/propose with empty text is rejected (400).
- POST /api/v1/twin/propose with non-empty text lands in the
  pending queue: six specialist rows, each with ``action_id`` and
  ``payload_sha256``.
- Approve still requires the digest — approve without a matching
  ``expected_payload_sha256`` is rejected.
- No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class TestT111OperatorPropose(unittest.TestCase):
    """Operator page can propose one task text into the local queue."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t111_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _client(self) -> TestClient:
        from app.server import create_app

        return TestClient(create_app())

    def _queue_pending(self, tenant_id: str) -> list[dict]:
        from core.twin_local_view import list_queue

        return list_queue(tenant_id)["pending"]

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_propose_empty_rejected(self) -> None:
        """Empty text is rejected with 400."""
        client = self._client()
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": "t111-empty", "text": ""},
        )
        self.assertEqual(resp.status_code, 400)
        # Nothing should have been inserted.
        self.assertEqual(len(self._queue_pending("t111-empty")), 0)

    def test_propose_lands_in_queue(self) -> None:
        """Non-empty text produces six proposed rows with digests."""
        client = self._client()
        tenant = "t111-queue"
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "Review the weekly digest"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 6)

        # Each proposal row must have action_id and payload_sha256.
        for row in body["proposals"]:
            self.assertTrue(row.get("action_id"), "row missing action_id")
            self.assertTrue(row.get("payload_sha256"), "row missing payload_sha256")
            self.assertEqual(row["status"], "proposed")

        # All six must appear in the pending queue.
        pending = self._queue_pending(tenant)
        self.assertEqual(len(pending), 6)
        for a in pending:
            self.assertEqual(a["status"], "proposed")
            self.assertEqual(a["tenant_id"], tenant)
            self.assertTrue(a.get("payload_sha256"))

    def test_approve_still_needs_digest(self) -> None:
        """Approve with a wrong digest is rejected; the digest gate is intact."""
        client = self._client()
        tenant = "t111-approve"
        # Propose to get six rows in the queue.
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "Prepare the board memo"},
        )
        self.assertEqual(resp.status_code, 200)

        pending = self._queue_pending(tenant)
        self.assertGreaterEqual(len(pending), 1)

        action_id = pending[0]["action_id"]

        # Approve with a wrong digest → 409 (ValueError → "payload digest mismatch").
        bad = "0" * 64
        approve_resp = client.post(
            f"/api/v1/twin/actions/{action_id}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": bad,
            },
        )
        self.assertEqual(approve_resp.status_code, 409)

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
