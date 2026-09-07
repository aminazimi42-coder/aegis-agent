"""T112 — Distinct specialist proposals, still propose-only.

Covers:
- test_six_bodies_not_identical: each specialist produces a distinct,
  role-shaped ``body`` in the proposal payload.
- test_each_name_in_own_row: the six names each appear in exactly one
  queue row (by ``kind`` prefix ``{name}:propose``).
- test_still_propose_only: every row stays ``proposed``; no row is
  executed or approved.
- No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class TestT112DistinctProposals(unittest.TestCase):
    """Each specialist's proposal body is distinct and still propose-only."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t112_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _client(self) -> TestClient:
        from app.server import create_app

        return TestClient(create_app())

    def _propose(self, tenant_id: str, text: str) -> dict:
        client = self._client()
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant_id, "text": text},
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_six_bodies_not_identical(self) -> None:
        """All six payload ``body`` values are pairwise distinct."""
        body = self._propose("t112-distinct", "Review the board memo")
        proposals = body["proposals"]
        self.assertEqual(len(proposals), 6)

        # Re-fetch from the queue to inspect the payload.
        from core.twin_local_view import list_queue

        pending = list_queue("t112-distinct")["pending"]
        self.assertEqual(len(pending), 6)

        bodies = []
        for row in pending:
            payload = row.get("payload")
            if isinstance(payload, dict):
                bodies.append(payload.get("body"))
            elif isinstance(payload, str):
                # payload may be JSON string
                import json

                try:
                    decoded = json.loads(payload)
                    bodies.append(decoded.get("body"))
                except (json.JSONDecodeError, TypeError):
                    bodies.append(payload)
            else:
                bodies.append(None)

        # No body is None.
        for b in bodies:
            self.assertIsNotNone(b, "payload body must not be None")

        # All six must be distinct.
        self.assertEqual(len(set(bodies)), 6, f"bodies not distinct: {bodies!r}")

        # Each body must still include the operator text.
        for b in bodies:
            self.assertIn("Review the board memo", b)

    def test_each_name_in_own_row(self) -> None:
        """Each of the six names appears in exactly one ``kind``."""
        body = self._propose("t112-names", "Prepare the weekly plan")

        expected_names = {"Alina", "Kian", "Bita", "Aylin", "Ahmad", "Amin"}
        kinds = {p["kind"] for p in body["proposals"]}
        name_prefixes = {k.split(":")[0] for k in kinds}
        self.assertEqual(name_prefixes, expected_names)

        # Each name appears in exactly one row.
        from collections import Counter

        name_counts = Counter(p["kind"].split(":")[0] for p in body["proposals"])
        for name in expected_names:
            self.assertEqual(name_counts[name], 1, f"{name} appears more than once")

    def test_still_propose_only(self) -> None:
        """No specialist row is executed or approved — all stay ``proposed``."""
        body = self._propose("t112-only", "Audit the quarterly ledger")

        for p in body["proposals"]:
            self.assertEqual(p["status"], "proposed")

        # No row in the queue has status other than proposed.
        from core.twin_local_view import list_queue

        pending = list_queue("t112-only")["pending"]
        for row in pending:
            self.assertEqual(row["status"], "proposed")
            self.assertNotEqual(row["status"], "executed")
            self.assertNotEqual(row["status"], "approved")

        # payload_sha256 present on all rows.
        for row in pending:
            self.assertTrue(row.get("payload_sha256"))


if __name__ == "__main__":
    unittest.main()
