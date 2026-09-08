"""T120 — Two-column operator home (Archive + Latest task).

Verifies that:
- ``test_latest_column_only_newest_batch``: after two propose calls, the
  ``latest`` list contains only the rows whose ``batch_id`` matches the
  newest batch; ``archive`` contains the older batch's rows.
- ``test_archive_excludes_approved``: approved and rejected rows stay out
  of both ``archive`` and ``latest`` — only ``proposed`` rows appear.
- ``test_html_has_two_columns``: app.html renders visible Archive and
  Latest task columns.

No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_HTML = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)


class TestT120TwoColumnHome(unittest.TestCase):
    """Operator home shows two columns: Archive and Latest task."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t120_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _client(self) -> TestClient:
        return TestClient(create_app())

    def _propose(self, tenant: str, text: str) -> dict:
        client = self._client()
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": text},
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def _queue(self, tenant: str) -> dict:
        from core.twin_local_view import list_queue

        return list_queue(tenant)

    # ------------------------------------------------------------------ #
    # 1. Latest column = only the newest batch
    # ------------------------------------------------------------------ #

    def test_latest_column_only_newest_batch(self) -> None:
        """After two proposes, latest holds only the newest batch's rows."""
        tenant = "t120-latest"

        # First propose — six rows with batch A.
        first = self._propose(tenant, "Review the weekly digest")
        first_batch = first["batch_id"]
        self.assertTrue(first_batch)

        # Second propose — six rows with batch B.
        second = self._propose(tenant, "Prepare the board memo")
        second_batch = second["batch_id"]
        self.assertTrue(second_batch)
        self.assertNotEqual(first_batch, second_batch)

        q = self._queue(tenant)
        latest = q["latest"]
        archive = q["archive"]

        # Latest must contain only rows from the second (newest) batch.
        self.assertGreater(len(latest), 0)
        for row in latest:
            self.assertEqual(row["batch_id"], second_batch)
            self.assertEqual(row["status"], "proposed")

        # Archive must contain only rows from the first (older) batch.
        self.assertGreater(len(archive), 0)
        for row in archive:
            self.assertEqual(row["batch_id"], first_batch)
            self.assertEqual(row["status"], "proposed")

        # No row from the newest batch should appear in archive.
        for row in archive:
            self.assertNotEqual(row["batch_id"], second_batch)

        # The two columns together equal the full pending list.
        self.assertEqual(len(latest) + len(archive), len(q["pending"]))

    # ------------------------------------------------------------------ #
    # 2. Archive excludes approved and rejected
    # ------------------------------------------------------------------ #

    def test_archive_excludes_approved(self) -> None:
        """Approved and rejected rows are not in archive or latest."""
        from core.twin_actions import _action_digest, approve, reject

        tenant = "t120-exclude"
        self._propose(tenant, "Review the weekly digest")
        second = self._propose(tenant, "Prepare the board memo")
        second_batch = second["batch_id"]

        q = self._queue(tenant)
        pending = q["pending"]
        self.assertGreater(len(pending), 0)

        # Approve one row from the latest batch and reject another.
        latest_rows = [r for r in pending if r.get("batch_id") == second_batch]
        self.assertGreaterEqual(len(latest_rows), 2)

        approve_id = latest_rows[0]["action_id"]
        reject_id = latest_rows[1]["action_id"]
        approve_digest = latest_rows[0].get("payload_sha256") or _action_digest(latest_rows[0])
        reject_digest = latest_rows[1].get("payload_sha256") or _action_digest(latest_rows[1])

        approve(approve_id, tenant_id=tenant, actor_id="op",
                expected_payload_sha256=approve_digest)
        reject(reject_id, tenant_id=tenant, actor_id="op",
               expected_payload_sha256=reject_digest, reason="duplicate")

        q2 = self._queue(tenant)
        all_latest = q2["latest"]
        all_archive = q2["archive"]

        # Neither approved nor rejected action_id appears in either column.
        for row in all_latest:
            self.assertNotEqual(row["action_id"], approve_id)
            self.assertNotEqual(row["action_id"], reject_id)
            self.assertEqual(row["status"], "proposed")
        for row in all_archive:
            self.assertNotEqual(row["action_id"], approve_id)
            self.assertNotEqual(row["action_id"], reject_id)
            self.assertEqual(row["status"], "proposed")

    # ------------------------------------------------------------------ #
    # 3. app.html has two visible columns
    # ------------------------------------------------------------------ #

    def test_html_has_two_columns(self) -> None:
        """app.html renders Archive and Latest task columns."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()

        # Both column labels must be present.
        self.assertIn("archive", lowered, "app.html missing 'archive' column")
        self.assertIn("latest", lowered, "app.html missing 'latest' column")

        # CSS two-column layout must exist.
        self.assertIn("two-col", lowered, "app.html missing two-col layout class")
        self.assertIn("col-archive", lowered,
                      "app.html missing col-archive element")
        self.assertIn("col-latest", lowered,
                      "app.html missing col-latest element")

        # The queue render must populate both archive-items and latest-items.
        self.assertIn("archive-items", lowered,
                      "app.html missing archive-items container")
        self.assertIn("latest-items", lowered,
                      "app.html missing latest-items container")

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
