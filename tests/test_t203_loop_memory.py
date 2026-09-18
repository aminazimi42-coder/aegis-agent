"""T203 — Loop memory: weekly brief cites last approve/reject; session restore.

Covers:

* ``test_weekly_brief_cites_last_approve_when_present`` — the weekly brief
  markdown includes the last approved specialist name plus action-id prefix.
* ``test_weekly_brief_cites_last_reject_when_present`` — the weekly brief
  markdown includes the last reject reason (T117 enum).
* ``test_weekly_brief_omits_cite_when_no_history`` — the brief omits both
  cites when the tenant has no prior approve or reject.
* ``test_neighbor_tenant_notes_do_not_leak`` — neighbor tenant notes do
  not appear in the brief.
* ``test_session_id_restores_after_restart`` — after a propose writes a
  receipt, Start Session returns the prior session id.
* ``test_last_task_restores_after_restart`` — the last task string restores
  from the local receipt after an engine sleep.
* ``test_missing_receipt_starts_new_session`` — when no receipt exists,
  Start Session starts a new session id (typed, not a crash).
* ``test_weekly_brief_does_not_execute`` — the weekly brief does not
  execute or approve any row.
* ``test_readme_author_untouched`` — the README Author paragraph is intact.
* ``test_readme_does_not_contain_notarized`` — README has no ``notarized``.

Uses ``tmp_path`` as ``AEGIS_DATA_DIR``.  Does not write the live
``$HOME/.aegis``.  Does not start uvicorn.  No skip markers.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from core.twin_actions import (
    _action_digest,
    _load_action,
    approve,
    insert_specialist_proposal,
    list_actions,
    reject,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"
_NF = "not" + "arized"  # constructed at runtime to avoid self-trip
_xm = "pytest.mark." + "xf" + "ail"  # forbidden marker, built from pieces
_sk = "pytest." + "skip"  # forbidden skip, built from pieces


class TestT203LoopMemory(unittest.TestCase):
    """T203 — weekly brief cites last approve/reject; session restore."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t203_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete interview and return the session id."""
        state = start_session(tenant_id)
        sid = state["session_id"]
        for q in QUESTIONS:
            state = answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    def _insert_and_approve(self, tenant: str) -> str:
        """Insert one proposal, approve it, and return the action_id."""
        row = insert_specialist_proposal(
            tenant_id=tenant,
            agent_name="Alina",
            title="T203 approve cite",
            payload={"body": "approve test"},
            batch_id="batch-t203-appr-001",
        )
        action_id = row["action_id"]
        digest = row["payload_sha256"]
        approve(
            action_id=action_id,
            tenant_id=tenant,
            actor_id="operator",
            expected_payload_sha256=digest,
        )
        return action_id

    def _insert_and_reject(self, tenant: str, reason_enum: str = "WRONG_TIMING") -> str:
        """Insert one proposal, reject it, and return the action_id."""
        row = insert_specialist_proposal(
            tenant_id=tenant,
            agent_name="Kian",
            title="T203 reject cite",
            payload={"body": "reject test"},
            batch_id="batch-t203-rej-001",
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        reject(
            action_id=action_id,
            tenant_id=tenant,
            reason_enum=reason_enum,
            expected_payload_sha256=digest,
        )
        return action_id

    # ------------------------------------------------------------------ #
    # 1) Weekly brief cites last approve when present
    # ------------------------------------------------------------------ #

    def test_weekly_brief_cites_last_approve_when_present(self) -> None:
        """The weekly brief markdown includes the last approved specialist
        name plus action-id prefix."""
        from core.twin_morning_brief import render_brief

        tenant = "t203_approve_cite"
        self._full_interview(tenant)
        action_id = self._insert_and_approve(tenant)

        result = render_brief(tenant)
        brief_path = Path(result["path"])
        text = brief_path.read_text(encoding="utf-8")
        self.assertIn("Last approve:", text)
        self.assertIn("Alina", text)
        # action-id prefix (first 12 chars) should appear.
        self.assertIn(action_id[:12], text)

    # ------------------------------------------------------------------ #
    # 2) Weekly brief cites last reject when present
    # ------------------------------------------------------------------ #

    def test_weekly_brief_cites_last_reject_when_present(self) -> None:
        """The weekly brief markdown includes the last reject reason."""
        from core.twin_morning_brief import render_brief

        tenant = "t203_reject_cite"
        self._full_interview(tenant)
        self._insert_and_reject(tenant, "POLICY_VIOLATION")

        result = render_brief(tenant)
        brief_path = Path(result["path"])
        text = brief_path.read_text(encoding="utf-8")
        self.assertIn("Last reject:", text)
        self.assertIn("POLICY_VIOLATION", text)

    # ------------------------------------------------------------------ #
    # 3) Weekly brief omits cite when no history
    # ------------------------------------------------------------------ #

    def test_weekly_brief_omits_cite_when_no_history(self) -> None:
        """The brief omits both cites when the tenant has no prior
        approve or reject."""
        from core.twin_morning_brief import render_brief

        tenant = "t203_no_history"
        self._full_interview(tenant)
        result = render_brief(tenant)
        brief_path = Path(result["path"])
        text = brief_path.read_text(encoding="utf-8")
        self.assertNotIn("Last approve:", text)
        self.assertNotIn("Last reject:", text)
        # The return dict carries None for both.
        self.assertIsNone(result.get("last_approve_cite"))
        self.assertIsNone(result.get("last_reject_reason"))

    # ------------------------------------------------------------------ #
    # 4) Neighbor tenant notes do not leak
    # ------------------------------------------------------------------ #

    def test_neighbor_tenant_notes_do_not_leak(self) -> None:
        """Neighbor tenant notes do not appear in the brief."""
        from core.twin_morning_brief import render_brief

        tenant_a = "t203_neighbor_a"
        tenant_b = "t203_neighbor_b"
        self._full_interview(tenant_a)
        self._full_interview(tenant_b)
        # Tenant A has an approve.
        self._insert_and_approve(tenant_a)
        # Tenant B has a reject.
        self._insert_and_reject(tenant_b, "DUPLICATE")

        # Render brief for tenant A — should see A's approve but not B's reject.
        result_a = render_brief(tenant_a)
        text_a = Path(result_a["path"]).read_text(encoding="utf-8")
        self.assertIn("Last approve:", text_a)
        self.assertNotIn("DUPLICATE", text_a)

        # Render brief for tenant B — should see B's reject but not A's approve.
        result_b = render_brief(tenant_b)
        text_b = Path(result_b["path"]).read_text(encoding="utf-8")
        self.assertIn("Last reject:", text_b)
        self.assertIn("DUPLICATE", text_b)
        # B has no approve.
        self.assertNotIn("Last approve:", text_b)

    # ------------------------------------------------------------------ #
    # 5) Session id restores after restart
    # ------------------------------------------------------------------ #

    def test_session_id_restores_after_restart(self) -> None:
        """After a propose writes a receipt, Start Session returns the
        prior session id."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t203_session_restore"
        self._full_interview(tenant)

        client = TestClient(create_app())
        # Propose to write a session receipt.
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "restore me task"},
        )
        self.assertEqual(resp.status_code, 200)

        # Simulate restart: call Start Session again — should return the
        # prior session id stored in the receipt.
        resp2 = client.post(
            "/api/v1/twin/session/start",
            json={"tenant_id": tenant},
        )
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.json()
        self.assertIn("session_id", body2)
        # The session_id should be non-empty.
        self.assertTrue(body2["session_id"])
        # The session_id should match the one in the receipt file.
        receipts_dir = Path(self._tmp) / "receipts"
        files = list(receipts_dir.glob("session_*.json"))
        self.assertGreater(len(files), 0)
        receipt_data = json.loads(files[0].read_text("utf-8"))
        self.assertEqual(body2["session_id"], receipt_data["session_id"])

    # ------------------------------------------------------------------ #
    # 6) Last task restores after restart
    # ------------------------------------------------------------------ #

    def test_last_task_restores_after_restart(self) -> None:
        """The last task string restores from the local receipt after an
        engine sleep."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t203_last_task_restore"
        self._full_interview(tenant)

        client = TestClient(create_app())
        task_text = "the last task text for restore"
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": task_text},
        )
        self.assertEqual(resp.status_code, 200)

        # Simulate restart.
        resp2 = client.post(
            "/api/v1/twin/session/start",
            json={"tenant_id": tenant},
        )
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.json()
        self.assertEqual(body2.get("last_task"), task_text)

    # ------------------------------------------------------------------ #
    # 7) Missing receipt starts new session
    # ------------------------------------------------------------------ #

    def test_missing_receipt_starts_new_session(self) -> None:
        """When no receipt exists, Start Session starts a new session id
        (typed, not a crash)."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t203_missing_receipt"
        # No propose, no receipt — just call Start Session.
        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/session/start",
            json={"tenant_id": tenant},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("session_id", body)
        self.assertTrue(body["session_id"].startswith("twin-"))
        self.assertEqual(body.get("last_task"), "")
        self.assertFalse(body.get("restored", False))

    # ------------------------------------------------------------------ #
    # 8) Weekly brief does not execute
    # ------------------------------------------------------------------ #

    def test_weekly_brief_does_not_execute(self) -> None:
        """The weekly brief does not execute or approve any row."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t203_no_execute"
        self._full_interview(tenant)

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "weekly_brief": True},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for p in body.get("proposals", []):
            self.assertEqual(p.get("status"), "proposed")
            self.assertNotEqual(p.get("status"), "executed")
            self.assertNotEqual(p.get("status"), "approved")

        # Also verify no action in the tenant is executed or approved.
        actions = list_actions(tenant)
        for a in actions:
            self.assertEqual(a.get("status"), "proposed")

    # ------------------------------------------------------------------ #
    # 9) README Author untouched
    # ------------------------------------------------------------------ #

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and unchanged."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 10) README does not contain notarized
    # ------------------------------------------------------------------ #

    def test_readme_does_not_contain_notarized(self) -> None:
        """The word *notarized* does not appear in the README."""
        text = _README.read_text(encoding="utf-8")
        lower = text.lower()
        self.assertNotIn(_NF, lower)

    # ------------------------------------------------------------------ #
    # No skip markers in this test file
    # ------------------------------------------------------------------ #

    def test_no_skip_markers_in_source(self) -> None:
        """This test file does not use skip markers."""
        src = Path(__file__).read_text(encoding="utf-8")
        self.assertNotIn(_xm, src)
        self.assertNotIn(_sk, src)


if __name__ == "__main__":
    unittest.main()
