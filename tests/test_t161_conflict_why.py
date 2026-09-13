"""T161 — Conflict tag depth + why-this-card from receipt.

Tests:
1. test_conflict_tag_when_prior_action_same_tenant
   — A new propose whose topic collides with a stored approved or
   rejected action for the same tenant gets ``conflict=True`` and
   carries ``prior_action_id`` plus ``prior_digest``.
2. test_conflict_tag_does_not_leak_neighbor_tenant
   — A prior action for tenant A does not cause a conflict tag for a
   new propose on tenant B (different tenant, same topic).
3. test_why_line_comes_from_receipt_not_http
   — The ``why`` line is short receipt text (the prior ``why_text`` or a
   deterministic prior-id line), not an HTTP call.  No network.
4. test_conflict_still_requires_approve
   — A conflicting row stays ``proposed``; ``execute()`` raises
   ``PermissionError`` until a human approves.
5. test_readme_mentions_conflict_and_why
   — README Now mentions both ``conflict`` and ``why``.

No uvicorn.  Uses ``tmp_path`` (``tempfile.mkdtemp``).  Does not write
the developer's real ``$HOME/.aegis``.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from fastapi.testclient import TestClient


class TestT161ConflictWhy(unittest.TestCase):
    """Conflict tag depth and receipt-backed why line on the operator card."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t161_")
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

    def _pending(self, tenant_id: str) -> list[dict]:
        from core.twin_local_view import list_queue

        return list_queue(tenant_id)["pending"]

    def _approve_row(self, tenant_id: str, action_id: str, digest: str) -> dict:
        from core.twin_actions import approve

        return approve(action_id, tenant_id, "operator", digest)

    def _reject_row(
        self,
        tenant_id: str,
        action_id: str,
        digest: str,
        why: str = "stale topic",
    ) -> dict:
        from core.twin_actions import reject

        return reject(
            action_id,
            tenant_id,
            reason="stale",
            why=why,
            expected_payload_sha256=digest,
        )

    # ------------------------------------------------------------------ #
    # 1) Conflict tag when prior action for same tenant
    # ------------------------------------------------------------------ #

    def test_conflict_tag_when_prior_action_same_tenant(self) -> None:
        """A new propose colliding with a prior approved action for the
        same tenant gets ``conflict=True`` with ``prior_action_id`` and
        ``prior_digest``."""
        tenant = "t161-conflict-same"
        topic = "Review the quarterly security audit"

        # First propose — creates six proposed rows.
        self._propose(tenant, topic)

        # Approve one row so there is an approved action with a digest.
        pending = self._pending(tenant)
        self.assertGreaterEqual(len(pending), 1)
        row = pending[0]
        action_id = row["action_id"]
        digest = row.get("payload_sha256", "")
        self._approve_row(tenant, action_id, digest)

        # Second propose with the same topic text — at least the row
        # whose title matches the approved action should be tagged
        # conflict=True and carry prior_action_id + prior_digest.
        body = self._propose(tenant, topic)
        rows_with_prior = [
            p
            for p in body["proposals"]
            if p.get("prior_action_id") is not None
        ]
        self.assertGreaterEqual(
            len(rows_with_prior),
            1,
            "expected at least one proposal with prior_action_id",
        )
        for c in rows_with_prior:
            self.assertTrue(c["conflict"])
            self.assertIsNotNone(c.get("prior_action_id"))
            self.assertIsNotNone(c.get("prior_digest"))
            self.assertIsInstance(c.get("why"), str)
            self.assertTrue(c["why"].strip())

    # ------------------------------------------------------------------ #
    # 2) Conflict tag does not leak to neighbor tenant
    # ------------------------------------------------------------------ #

    def test_conflict_tag_does_not_leak_neighbor_tenant(self) -> None:
        """A prior approved action for tenant A does not tag a propose for
        tenant B even when the topic text is identical."""
        tenant_a = "t161-neighbor-a"
        tenant_b = "t161-neighbor-b"
        topic = "Review the quarterly security audit"

        # Tenant A: propose + approve one row.
        self._propose(tenant_a, topic)
        pending_a = self._pending(tenant_a)
        row_a = pending_a[0]
        self._approve_row(
            tenant_a, row_a["action_id"], row_a.get("payload_sha256", "")
        )

        # Tenant B: propose the same topic — must NOT be conflict-tagged.
        body_b = self._propose(tenant_b, topic)
        for p in body_b["proposals"]:
            self.assertFalse(
                p.get("conflict", False),
                "neighbor tenant must not see the conflict tag",
            )
            self.assertIsNone(p.get("prior_action_id"))
            self.assertIsNone(p.get("prior_digest"))

    # ------------------------------------------------------------------ #
    # 3) Why line comes from receipt, not HTTP
    # ------------------------------------------------------------------ #

    def test_why_line_comes_from_receipt_not_http(self) -> None:
        """The why line is short receipt text from the prior action's
        ``why_text``, not an HTTP call."""
        tenant = "t161-why-receipt"
        topic = "Review the quarterly compliance report"

        # First propose + reject with a why_text.
        self._propose(tenant, topic)
        pending = self._pending(tenant)
        row = pending[0]
        reject_reason = "duplicate of prior audit"
        self._reject_row(
            tenant,
            row["action_id"],
            row.get("payload_sha256", ""),
            why=reject_reason,
        )

        # Second propose with the same topic — the row whose title
        # matches the rejected action should carry a why line derived
        # from the stored why_text, not an HTTP call.
        body = self._propose(tenant, topic)
        rows_with_prior = [
            p for p in body["proposals"] if p.get("prior_action_id")
        ]
        self.assertGreaterEqual(len(rows_with_prior), 1)
        for c in rows_with_prior:
            why = c.get("why", "")
            self.assertIsInstance(why, str)
            self.assertTrue(why.strip())
            # The why text must contain the reject reason text (it is
            # derived from the stored why_text, not an HTTP call).
            self.assertIn(reject_reason, why)

    # ------------------------------------------------------------------ #
    # 4) Conflict still requires Approve
    # ------------------------------------------------------------------ #

    def test_conflict_still_requires_approve(self) -> None:
        """A conflict-tagged row stays ``proposed`` and ``execute()``
        raises ``PermissionError`` until a human approves it."""
        from core.twin_actions import execute

        tenant = "t161-conflict-approve"
        topic = "Review the annual budget plan"

        # Create a prior approved action.
        self._propose(tenant, topic)
        pending = self._pending(tenant)
        row = pending[0]
        self._approve_row(
            tenant, row["action_id"], row.get("payload_sha256", "")
        )

        # Second propose — at least the row whose title matches the
        # approved action is conflict-tagged with a prior id.
        self._propose(tenant, topic)
        new_pending = self._pending(tenant)
        conflict_rows = [
            r for r in new_pending if r.get("prior_action_id")
        ]
        self.assertGreaterEqual(len(conflict_rows), 1)

        # Every conflict row is still ``proposed`` and execute() raises.
        for c in conflict_rows:
            self.assertEqual(c["status"], "proposed")
            with self.assertRaises(PermissionError):
                execute(c["action_id"], tenant)

    # ------------------------------------------------------------------ #
    # 5) README mentions conflict and why
    # ------------------------------------------------------------------ #

    def test_readme_mentions_conflict_and_why(self) -> None:
        """README Now mentions both ``conflict`` and ``why``."""
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        readme = (repo_root / "README.md").read_text(encoding="utf-8")
        lower = readme.lower()
        self.assertIn("conflict", lower)
        self.assertIn("why", lower)


if __name__ == "__main__":
    unittest.main()
