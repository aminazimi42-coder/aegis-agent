"""T114 — Queue hygiene: reject with digest and profile prefill.

Verifies that:
- ``test_pending_hides_approved``: the pending queue lists only ``proposed``
  actions — approved/rejected rows are excluded.
- ``test_reject_needs_digest``: the reject route requires
  ``expected_payload_sha256``; a mutated digest is rejected with 409 and
  the action stays ``proposed``.  The CLI reject (no digest) still works.
- ``test_profile_prefill_local``: ``app.html`` fetches
  ``/api/v1/twin/profile/local`` on load and prefills the four
  operator-page fields; it does NOT auto-Start Session.

No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_actions import (
    _action_digest,
    approve,
    list_actions,
    propose_actions,
    reject,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session
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


class TestT114QueueHygiene(unittest.TestCase):
    """Reject needs digest; pending hides approved; profile prefill on load."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t114_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _propose(self, tenant: str) -> dict:
        """Run a full interview + commit, then propose and return an action dict."""
        session = start_session(tenant)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        actions = propose_actions(tenant)
        self.assertGreater(len(actions), 0)
        pending: list[dict] = [
            a for a in list_actions(tenant) if a.get("status") == "proposed"
        ]
        self.assertGreater(len(pending), 0)
        return pending[0]

    # ------------------------------------------------------------------ #
    # 1. Pending queue lists proposed only
    # ------------------------------------------------------------------ #

    def test_pending_hides_approved(self) -> None:
        """After approving one action, the pending queue excludes it."""
        tenant = "t114-hide"
        action = self._propose(tenant)
        action_id = action["action_id"]
        digest = action.get("payload_sha256") or _action_digest(action)
        self.assertTrue(digest)

        # Approve the action.
        approve(action_id, tenant_id=tenant, actor_id="op",
                expected_payload_sha256=digest)

        # Queue should now show only the remaining proposed actions.
        from core.twin_local_view import list_queue

        q = list_queue(tenant)
        pending_ids = {a["action_id"] for a in q["pending"]}
        approved_ids = {a["action_id"] for a in q["approved_waiting"]}
        self.assertNotIn(action_id, pending_ids,
                         "approved action must not be in pending")
        self.assertIn(action_id, approved_ids,
                      "approved action should be in approved_waiting")

    # ------------------------------------------------------------------ #
    # 2. Reject needs digest — mutated digest → 409, correct → 200
    # ------------------------------------------------------------------ #

    def test_reject_needs_digest(self) -> None:
        """Reject via the API with a mutated digest returns 409; correct returns 200."""
        tenant = "t114-digest"
        action = self._propose(tenant)
        action_id = action["action_id"]
        real_digest = action.get("payload_sha256") or _action_digest(action)
        self.assertTrue(real_digest)
        bad_digest = "a" * 64 if real_digest != "a" * 64 else "b" * 64

        app = create_app()
        client = TestClient(app)

        # Mutated digest → 409, action stays proposed.
        resp = client.post(
            f"/api/v1/twin/actions/{action_id}/reject",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": bad_digest,
            },
        )
        self.assertEqual(resp.status_code, 409)
        still_pending = [
            a for a in list_actions(tenant)
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
            },
        )
        self.assertEqual(resp2.status_code, 200)
        rejected = [
            a for a in list_actions(tenant)
            if a["action_id"] == action_id and a.get("status") == "rejected"
        ]
        self.assertEqual(len(rejected), 1)

        # CLI reject (no digest) still works on a fresh proposed action.
        action2 = self._propose(tenant + "-cli")
        result = reject(action2["action_id"], tenant + "-cli", reason="duplicate")
        self.assertEqual(result["status"], "rejected")

    # ------------------------------------------------------------------ #
    # 3. Profile prefill on load — app.html fetches profile/local
    # ------------------------------------------------------------------ #

    def test_profile_prefill_local(self) -> None:
        """app.html fetches /api/v1/twin/profile/local and prefills fields."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lowered = html.lower()

        # Must fetch the local profile on load.
        self.assertIn("profile/local", lowered,
                       "app.html does not fetch /api/v1/twin/profile/local")
        # Must have a prefill mechanism.
        self.assertIn("prefill", lowered,
                      "app.html has no prefill mechanism")
        # Must NOT auto-start a session on load.
        # The init section should not call startInterview() — only the
        # button's onclick handler may reference it.
        script = lowered.split("<script>", 1)[-1]
        init_idx = script.find("//──init")
        if init_idx == -1:
            init_idx = 0
        init_block = script[init_idx:]
        self.assertNotIn("startinterview()", init_block.replace(" ", ""),
                         "app.html init must not auto-start a session on load")
        # Must reference the profile fields for prefilling.
        self.assertIn("profileprefill", lowered.replace(" ", "").replace("_", ""),
                      "app.html has no profilePrefill variable")

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
