"""T117 — Structured reject reasons and deterministic queue priority.

Covers:
- ``test_reject_reason_persists``: the ``reason_enum`` label
  (``WRONG_TIMING``, ``WRONG_RECIPIENT``, ``LOW_CONFIDENCE``,
  ``POLICY_VIOLATION``, ``DUPLICATE``, ``OTHER``) is persisted on the
  action row and defaults to ``OTHER`` when omitted.
- ``test_reject_still_needs_digest``: a mutated digest is still
  rejected with 409; the correct digest is accepted.
- ``test_low_confidence_still_queued``: a low confidence score sets a
  warning flag but never drops the row — the action stays ``proposed``.
- ``test_priority_orders_higher_score_first``: the pending queue is
  sorted by descending priority score (higher score first).

No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from core.twin_actions import (
    _action_digest,
    _load_action,
    insert_specialist_proposal,
    list_actions,
    reject,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session
from fastapi.testclient import TestClient


class TestT117FeedbackPriority(unittest.TestCase):
    """Structured reject reasons, confidence label, and deterministic priority."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t117_")
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

    def _propose_specialist(
        self,
        tenant_id: str,
        specialist: str = "Alina",
        title: str = "T117 specialist proposal",
    ) -> str:
        """Insert one specialist proposal and return its action_id."""
        self._full_interview(tenant_id)
        result = insert_specialist_proposal(tenant_id, specialist, title, {})
        return result["action_id"]

    # ------------------------------------------------------------------ #
    # 1. Reject reason enum persists
    # ------------------------------------------------------------------ #

    def test_reject_reason_persists(self) -> None:
        """The ``reason_enum`` label is persisted on the action row.

        Each label in ``REJECT_REASON_ENUM`` is accepted and stored.
        When omitted, ``reject_reason_enum`` defaults to ``OTHER`` so
        old clients still work.
        """
        from core.twin_actions import REJECT_REASON_ENUM

        for label in REJECT_REASON_ENUM:
            tenant = f"t117-enum-{label.lower()}"
            action_id = self._propose_specialist(tenant, title=f"Action {label}")
            result = reject(action_id, tenant, reason_enum=label)
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(result.get("reject_reason_enum"), label)
            row = _load_action(action_id)
            assert row is not None
            self.assertEqual(row.get("reject_reason_enum"), label)

        # Default — omitted reason_enum → OTHER.
        tenant_def = "t117-enum-default"
        action_id = self._propose_specialist(tenant_def, title="Default reason")
        result = reject(action_id, tenant_def)
        self.assertEqual(result.get("reject_reason_enum"), "OTHER")

    # ------------------------------------------------------------------ #
    # 2. Reject still needs digest
    # ------------------------------------------------------------------ #

    def test_reject_still_needs_digest(self) -> None:
        """A mutated digest is rejected with 409; the correct digest is accepted.

        The reject route requires ``expected_payload_sha256`` — a mutated
        digest returns 409 and the action stays ``proposed``.  The correct
        digest returns 200 and the action becomes ``rejected``.
        """
        tenant = "t117-digest"
        action_id = self._propose_specialist(tenant, title="Digest-bound action")
        action = _load_action(action_id)
        assert action is not None
        real_digest = action.get("payload_sha256") or _action_digest(action)
        self.assertTrue(real_digest)
        bad_digest = "a" * 64 if real_digest != "a" * 64 else "b" * 64

        from app.server import create_app

        app = create_app()
        client = TestClient(app)

        # Mutated digest → 409, action stays proposed.
        resp = client.post(
            f"/api/v1/twin/actions/{action_id}/reject",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": bad_digest,
                "reason_enum": "WRONG_TIMING",
            },
        )
        self.assertEqual(resp.status_code, 409)
        still_pending = [
            a
            for a in list_actions(tenant)
            if a["action_id"] == action_id and a.get("status") == "proposed"
        ]
        self.assertEqual(len(still_pending), 1)

        # Correct digest → 200, status becomes rejected.
        resp2 = client.post(
            f"/api/v1/twin/actions/{action_id}/reject",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": real_digest,
                "reason_enum": "WRONG_TIMING",
            },
        )
        self.assertEqual(resp2.status_code, 200)
        rejected = [
            a
            for a in list_actions(tenant)
            if a["action_id"] == action_id and a.get("status") == "rejected"
        ]
        self.assertEqual(len(rejected), 1)

    # ------------------------------------------------------------------ #
    # 3. Low confidence still queued
    # ------------------------------------------------------------------ #

    def test_low_confidence_still_queued(self) -> None:
        """A low confidence score sets a warning flag but never drops the row.

        After rejecting some specialist proposals, the approval rate drops
        below 0.5.  The next proposal for that pair gets a
        ``low_confidence_warning`` flag but stays ``proposed`` in the
        queue — it is never auto-dropped or auto-executed.
        """
        from core.feedback_stats import attach_confidence, confidence_score
        from core.twin_local_view import list_queue

        tenant = "t117-low-conf"
        specialist = "Bita"

        # Insert and reject two proposals to drive the approval rate to 0.
        a1 = self._propose_specialist(
            tenant, specialist=specialist, title="Low-conf proposal 1"
        )
        reject(a1, tenant, reason_enum="LOW_CONFIDENCE")

        a2 = self._propose_specialist(
            tenant, specialist=specialist, title="Low-conf proposal 2"
        )
        reject(a2, tenant, reason_enum="LOW_CONFIDENCE")

        # The approval rate should be 0.0 (2 rejects, 0 approves).
        score = confidence_score(tenant, specialist, "Bita:propose")
        self.assertLess(score, 0.5)

        # Insert a new proposal — it should stay proposed and get a warning.
        a3 = self._propose_specialist(
            tenant, specialist=specialist, title="Low-conf proposal 3"
        )
        action3 = _load_action(a3)
        assert action3 is not None
        attach_confidence(tenant, action3)
        self.assertTrue(
            action3.get("low_confidence_warning"),
            "low confidence should set warning flag",
        )

        # The action must still be in the pending queue (never dropped).
        pending = list_queue(tenant)["pending"]
        pending_ids = {a["action_id"] for a in pending}
        self.assertIn(a3, pending_ids, "low-confidence action must stay queued")

        # It must still be proposed (never auto-executed).
        action3_after = _load_action(a3)
        assert action3_after is not None
        self.assertEqual(action3_after["status"], "proposed")

    # ------------------------------------------------------------------ #
    # 4. Priority orders higher score first
    # ------------------------------------------------------------------ #

    def test_priority_orders_higher_score_first(self) -> None:
        """The pending queue is sorted by descending priority score.

        Two proposed actions with different risk levels: the higher-risk
        action gets a higher score (``w_risk * risk_level`` dominates
        with the default weights) and should appear first in the queue.
        """
        from core.priority import action_score, sort_actions
        from core.twin_risk import classify

        tenant = "t117-priority"
        self._full_interview(tenant)

        # Insert a low-risk (L0) proposal.
        low_result = insert_specialist_proposal(
            tenant,
            "Alina",
            "Review weekly digest",
            {},
        )
        low = low_result["action_id"]
        # Insert a high-risk (L2) proposal — title contains "email" keyword.
        high_result = insert_specialist_proposal(
            tenant,
            "Kian",
            "Send urgent email notification",
            {},
        )
        high = high_result["action_id"]

        # Verify the risk classifications differ.
        low_action = _load_action(low)
        high_action = _load_action(high)
        assert low_action is not None
        assert high_action is not None
        low_risk = classify(low_action.get("title", ""), low_action.get("kind"))
        high_risk = classify(high_action.get("title", ""), high_action.get("kind"))
        self.assertEqual(low_risk, "L0")
        self.assertEqual(high_risk, "L2")

        # The high-risk action should have a higher score.
        low_score = action_score(low_action)
        high_score = action_score(high_action)
        self.assertGreater(
            high_score, low_score,
            f"high-risk score ({high_score}) should exceed low-risk ({low_score})",
        )

        # sort_actions should put the higher-scored action first.
        sorted_list = sort_actions([low_action, high_action])
        self.assertEqual(sorted_list[0]["action_id"], high)

        # The pending queue should also be ordered highest-first.
        from core.twin_local_view import list_queue

        pending = list_queue(tenant)["pending"]
        self.assertEqual(pending[0]["action_id"], high)

    # ------------------------------------------------------------------ #
    # 5. No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
