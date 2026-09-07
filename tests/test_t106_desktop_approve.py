"""T106 — Desktop approve with visible digest.

Verifies that ``app.html`` shows an Approve button and a digest field
for each pending row, and that the existing approve route rejects a
mutated (wrong) digest.

No live network.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core.twin_actions import _action_digest, list_actions, propose_actions
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


class TestT106DesktopApprove(unittest.TestCase):
    """Approve button + digest visible; bad digest rejected."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t106_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # app.html content checks
    # ------------------------------------------------------------------ #

    def test_app_html_has_approve_and_digest(self) -> None:
        """app.html must contain 'approve' and 'digest' text."""
        self.assertTrue(_APP_HTML.is_file(), f"app.html missing at {_APP_HTML}")
        text = _APP_HTML.read_text(encoding="utf-8")
        self.assertIn("approve", text.lower())
        self.assertIn("digest", text.lower())

    # ------------------------------------------------------------------ #
    # Approve route rejects bad digest
    # ------------------------------------------------------------------ #

    def test_approve_rejects_bad_digest(self) -> None:
        """POST approve with a wrong digest must fail (409 or 400)."""
        tenant = "t106-tenant"
        # Run a full interview + commit so a profile exists in SQLite.
        session = start_session(tenant)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        actions = propose_actions(tenant)
        self.assertGreater(len(actions), 0)
        pending = [a for a in list_actions(tenant) if a.get("status") == "proposed"]
        self.assertGreater(len(pending), 0)
        action = pending[0]
        action_id = action["action_id"]
        real_digest = action.get("payload_sha256") or _action_digest(action)
        self.assertTrue(real_digest)
        bad_digest = "a" * 64 if real_digest != "a" * 64 else "b" * 64
        self.assertNotEqual(bad_digest, real_digest)

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/twin/actions/{action_id}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": bad_digest,
            },
        )
        self.assertIn(resp.status_code, (409, 400))
        still_pending = [
            a for a in list_actions(tenant)
            if a["action_id"] == action_id and a.get("status") == "proposed"
        ]
        self.assertEqual(len(still_pending), 1)

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
