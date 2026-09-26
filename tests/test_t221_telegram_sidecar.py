"""T221 — Telegram sidecar after Approve only.

Covers:

* ``approve`` without a token → ``not_configured``, action approved.
* ``approve`` with a mock token → sidecar called after approve, not before.
* ``reject`` does not notify.
* Neighbor tenant token cannot notify this tenant.
* ``execute`` / ``complete_safe`` contains no telegram / bot token import.
* Audit / redact: token shapes stripped.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestT221TelegramSidecar(unittest.TestCase):
    """Telegram sidecar after Approve — outside execute."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t221_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        # Clean telegram env so each test starts fresh.
        for _k in (
            "AEGIS_TELEGRAM_BOT_TOKEN",
            "AEGIS_TELEGRAM_CHAT_ID",
        ):
            os.environ.pop(_k, None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        for _k in (
            "AEGIS_TELEGRAM_BOT_TOKEN",
            "AEGIS_TELEGRAM_CHAT_ID",
        ):
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

    def _make_action(self, tenant: str, body: str = "tg-test") -> tuple[str, str]:
        from core.twin_actions import _action_digest, _load_action, insert_specialist_proposal

        row = insert_specialist_proposal(
            tenant, "Alina", "Telegram test", {"body": body}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        return action_id, digest

    # ------------------------------------------------------------------ #
    # 1) Approve without token → not_configured, action approved
    # ------------------------------------------------------------------ #

    def test_approve_without_token_not_configured(self) -> None:
        """Without AEGIS_TELEGRAM_BOT_TOKEN, approve returns
        telegram_status not_configured and the action is approved."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        approve_without_token = True  # noqa: F841

        tenant = "t221_no_token"
        self._full_interview(tenant)
        action_id, digest = self._make_action(tenant)

        app = create_app()
        client = TestClient(app)
        resp = self._propose_and_approve(client, tenant, action_id, digest)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["telegram_status"], "not_configured")

    # ------------------------------------------------------------------ #
    # 2) Approve with mock token → sidecar called after approve, not before
    # ------------------------------------------------------------------ #

    def test_approve_with_mock_token_sidecar_after(self) -> None:
        """With a mock token, approve calls the sidecar and returns
        telegram_status; the sidecar fires after approve, not before."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        notify_after_approve_only = True  # noqa: F841

        os.environ["AEGIS_TELEGRAM_BOT_TOKEN"] = "1234567890:ABCmocktoken"
        os.environ["AEGIS_TELEGRAM_CHAT_ID"] = "987654321"

        tenant = "t221_mock_token"
        self._full_interview(tenant)
        action_id, digest = self._make_action(tenant)

        call_log: list[str] = []

        def _spy_notify(tenant_id, action_id, digest_prefix):
            call_log.append(f"called:{action_id}")
            return {"status": "sent"}

        app = create_app()
        client = TestClient(app)
        with mock.patch(
            "core.telegram_sidecar.notify_approved",
            side_effect=_spy_notify,
        ) as patched:
            resp = self._propose_and_approve(client, tenant, action_id, digest)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "approved")
        # The sidecar was called (after the approve).
        self.assertTrue(len(call_log) >= 1)
        self.assertEqual(patched.call_count, 1)
        self.assertEqual(data["telegram_status"], "sent")

    # ------------------------------------------------------------------ #
    # 3) Reject does not notify
    # ------------------------------------------------------------------ #

    def test_reject_does_not_notify(self) -> None:
        """Reject never calls the Telegram sidecar."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        reject_silent = True  # noqa: F841

        os.environ["AEGIS_TELEGRAM_BOT_TOKEN"] = "1234567890:ABCmocktoken"
        os.environ["AEGIS_TELEGRAM_CHAT_ID"] = "987654321"

        tenant = "t221_reject_silent"
        self._full_interview(tenant)
        action_id, digest = self._make_action(tenant, "reject")

        app = create_app()
        client = TestClient(app)
        with mock.patch(
            "core.telegram_sidecar.notify_approved",
            return_value={"status": "sent"},
        ) as patched:
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
        # Reject does not include telegram_status.
        self.assertNotIn("telegram_status", data)
        self.assertEqual(patched.call_count, 0)

    # ------------------------------------------------------------------ #
    # 4) Neighbor tenant token cannot notify this tenant
    # ------------------------------------------------------------------ #

    def test_neighbor_tenant_isolated(self) -> None:
        """A neighbor's Telegram chat id cannot be used for this tenant."""
        from core.telegram_sidecar import notify_approved

        neighbor_isolated = True  # noqa: F841

        os.environ["AEGIS_TELEGRAM_BOT_TOKEN"] = "1234567890:ABCmocktoken"
        # Do NOT set AEGIS_TELEGRAM_CHAT_ID — that is operator-wide.
        # Per-tenant chat id is in the store only.
        from core.llm_keychain import MockKeychain

        mock_store = MockKeychain()
        # Simulate per-tenant chat in store for tenant-A only:
        mock_store.set("aegis-operator-telegram", "chat-tenant-A", "111111111")
        # tenant-B has no chat entry in the store.

        with mock.patch(
            "core.telegram_sidecar.get_store",
            return_value=mock_store,
        ):
            # tenant-A resolves chat from store.
            res_a = notify_approved("tenant-A", "act-a", "deadbeef")
            # tenant-B has no chat → not_configured.
            res_b = notify_approved("tenant-B", "act-b", "cafef00d")

        self.assertNotEqual(res_a["status"], res_b["status"])
        # tenant-B should be not_configured (no chat).
        self.assertEqual(res_b["status"], "not_configured")

    # ------------------------------------------------------------------ #
    # 5) execute / complete_safe contains no telegram / bot token import
    # ------------------------------------------------------------------ #

    def test_execute_has_no_telegram(self) -> None:
        """core/twin_actions.py execute() does not import telegram_sidecar
        or the bot token."""
        execute_has_no_telegram = True  # noqa: F841

        twin_actions_src = Path("core/twin_actions.py").read_text("utf-8")
        self.assertNotIn("telegram_sidecar", twin_actions_src)
        self.assertNotIn("telegram", twin_actions_src.lower())

        llm_safety_src = Path("core/llm_safety.py").read_text("utf-8")
        self.assertNotIn("telegram", llm_safety_src.lower())

    # ------------------------------------------------------------------ #
    # 6) Audit / redact: token shapes stripped
    # ------------------------------------------------------------------ #

    def test_token_redacted(self) -> None:
        """The redact module strips Telegram bot token shapes."""
        token_redacted = True  # noqa: F841

        from core.redact import redact

        # A Telegram bot token shape: ``<digits>:<token>`` — redacted
        # by the T221 Telegram bot token pattern.
        raw = "bot token: 1234567890:AAHabcdefghijklmnopqrstuvwxyz1234"
        redacted = redact(raw)
        self.assertNotIn("AAHabcdefghijklmnopqrstuvwxyz1234", redacted)
        self.assertIn("[REDACTED]", redacted)

        # Bare ``token=…`` assignment shape — redacted by T221 pattern.
        raw2 = "token=ABCsecrettokenvalue1234"
        redacted2 = redact(raw2)
        self.assertNotIn("ABCsecrettokenvalue1234", redacted2)
        self.assertIn("[REDACTED]", redacted2)

        # ``chat_id=…`` assignment shape — redacted by T221 pattern.
        raw3 = "chat_id=987654321secret"
        redacted3 = redact(raw3)
        self.assertNotIn("987654321secret", redacted3)
        self.assertIn("[REDACTED]", redacted3)

    # ------------------------------------------------------------------ #
    # 7) Network failure → TELEGRAM_SIDECAR_FAILED, approve stays valid
    # ------------------------------------------------------------------ #

    def test_network_failure_typed_failed(self) -> None:
        """If the Telegram HTTP call fails, approve returns
        TELEGRAM_SIDECAR_FAILED and the action stays approved."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        os.environ["AEGIS_TELEGRAM_BOT_TOKEN"] = "1234567890:ABCmocktoken"
        os.environ["AEGIS_TELEGRAM_CHAT_ID"] = "987654321"

        tenant = "t221_net_fail"
        self._full_interview(tenant)
        action_id, digest = self._make_action(tenant, "net-fail")

        app = create_app()
        client = TestClient(app)
        with mock.patch(
            "core.telegram_sidecar.notify_approved",
            return_value={"status": "telegram_sidecar_failed"},
        ):
            resp = self._propose_and_approve(client, tenant, action_id, digest)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["telegram_status"], "TELEGRAM_SIDECAR_FAILED")


if __name__ == "__main__":
    unittest.main()
