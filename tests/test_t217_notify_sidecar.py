"""T217 — Notify sidecar after Approve outside execute.

Covers:

* ``approve`` writes one outbox row when ``AEGIS_NOTIFY_WEBHOOK`` is set
  and the HTTP flag is off (default file-only).
* ``approve`` without the env returns ``not_configured`` and the action
  stays approved.
* A sidecar exception leaves the action approved (failure does not roll
  back).
* ``reject`` does not write an outbox row.
* ``core/`` has no Stripe token.
* Six specialist names only (no seventh agent).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestT217NotifySidecar(unittest.TestCase):
    """Notify sidecar after Approve — outside execute."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t217_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        # Clean notify env so each test starts fresh.
        for _k in ("AEGIS_NOTIFY_WEBHOOK", "AEGIS_NOTIFY_HTTP"):
            os.environ.pop(_k, None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        for _k in ("AEGIS_NOTIFY_WEBHOOK", "AEGIS_NOTIFY_HTTP"):
            os.environ.pop(_k, None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete T03 interview and return the session id."""
        from core.twin_interview import QUESTIONS, answer, commit, start_session

        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    def _propose_and_approve(
        self, client, tenant: str, action_id: str, digest: str
    ):
        """Approve *action_id* via the API route."""
        resp = client.post(
            f"/api/v1/twin/actions/{action_id}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": digest,
            },
        )
        return resp

    # ------------------------------------------------------------------ #
    # 1) Approve writes outbox row when webhook env set and HTTP flag off
    # ------------------------------------------------------------------ #

    def test_approve_writes_outbox_when_webhook_set(self) -> None:
        """When AEGIS_NOTIFY_WEBHOOK is set, approve writes one JSONL row."""
        from app.server import create_app
        from core.twin_actions import (
            _action_digest,
            _load_action,
            insert_specialist_proposal,
        )
        from fastapi.testclient import TestClient

        os.environ["AEGIS_NOTIFY_WEBHOOK"] = "https://hooks.example.com/test"
        tenant = "t217_approve_write"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Notify test", {"body": "approve-write"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)

        app = create_app()
        client = TestClient(app)
        resp = self._propose_and_approve(client, tenant, action_id, digest)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("notify_status", data)
        self.assertEqual(data["notify_status"], "file_written")

        # The outbox file exists with one JSONL row.
        outbox = Path(self._tmp) / "notify" / "outbox.jsonl"
        self.assertTrue(outbox.is_file(), f"outbox missing at {outbox}")
        lines = outbox.read_text("utf-8").strip().split("\n")
        self.assertEqual(len(lines), 1)
        row_data = json.loads(lines[0])
        self.assertEqual(row_data["event"], "approved")
        self.assertEqual(row_data["tenant_id"], tenant)
        self.assertEqual(row_data["action_id"], action_id)
        self.assertFalse(row_data["http"])  # HTTP flag off

    # ------------------------------------------------------------------ #
    # 2) Approve without env returns not_configured and still approved
    # ------------------------------------------------------------------ #

    def test_approve_without_env_returns_not_configured(self) -> None:
        """Without AEGIS_NOTIFY_WEBHOOK, approve returns not_configured
        and the action is still approved."""
        from app.server import create_app
        from core.twin_actions import (
            _action_digest,
            _load_action,
            insert_specialist_proposal,
        )
        from fastapi.testclient import TestClient

        tenant = "t217_no_env"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "No env test", {"body": "no-env"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)

        app = create_app()
        client = TestClient(app)
        resp = self._propose_and_approve(client, tenant, action_id, digest)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["notify_status"], "not_configured")
        self.assertEqual(data["status"], "approved")

        # No outbox file was created.
        outbox = Path(self._tmp) / "notify" / "outbox.jsonl"
        self.assertFalse(outbox.exists())

    # ------------------------------------------------------------------ #
    # 3) Sidecar exception leaves action approved
    # ------------------------------------------------------------------ #

    def test_sidecar_exception_leaves_approved(self) -> None:
        """If the sidecar raises, the action stays approved and the
        response carries sidecar_failed."""
        from app.server import create_app
        from core.twin_actions import (
            _action_digest,
            _load_action,
            insert_specialist_proposal,
        )
        from fastapi.testclient import TestClient

        os.environ["AEGIS_NOTIFY_WEBHOOK"] = "https://hooks.example.com/test"
        tenant = "t217_sidecar_fail"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Sidecar fail", {"body": "fail"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)

        app = create_app()
        client = TestClient(app)
        with mock.patch(
            "core.notify_sidecar.handle_approved_event",
            side_effect=RuntimeError("boom"),
        ):
            resp = self._propose_and_approve(client, tenant, action_id, digest)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["notify_status"], "sidecar_failed")

    # ------------------------------------------------------------------ #
    # 4) Reject does not write outbox
    # ------------------------------------------------------------------ #

    def test_reject_does_not_write_outbox(self) -> None:
        """Reject never calls the notify sidecar — no outbox row."""
        from app.server import create_app
        from core.twin_actions import (
            _action_digest,
            _load_action,
            insert_specialist_proposal,
        )
        from fastapi.testclient import TestClient

        os.environ["AEGIS_NOTIFY_WEBHOOK"] = "https://hooks.example.com/test"
        tenant = "t217_reject_silent"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Reject test", {"body": "reject"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/twin/actions/{action_id}/reject",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": digest,
                "reason_enum": "OTHER",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("notify_status", data)
        # No outbox file.
        outbox = Path(self._tmp) / "notify" / "outbox.jsonl"
        self.assertFalse(outbox.exists())

    # ------------------------------------------------------------------ #
    # 5) core/ has no Stripe token
    # ------------------------------------------------------------------ #

    def test_core_has_no_stripe(self) -> None:
        """No file under core/ contains the substring 'stripe'."""

        core_dir = Path("core")
        for p in core_dir.glob("*.py"):
            text = p.read_text("utf-8")
            self.assertNotRegex(
                text,
                r"(?i)stripe",
                f"'stripe' found in {p}",
            )

    # ------------------------------------------------------------------ #
    # 6) Six specialist names only
    # ------------------------------------------------------------------ #

    def test_six_specialists_only(self) -> None:
        """The agent registry has exactly six specialist names."""
        from core.agent_registry import AGENT_REGISTRY

        names = [spec.name for spec in AGENT_REGISTRY]
        self.assertEqual(len(names), 6)
        expected = {"Alina", "Kian", "Bita", "Aylin", "Ahmad", "Amin"}
        self.assertEqual(set(names), expected)


if __name__ == "__main__":
    unittest.main()
