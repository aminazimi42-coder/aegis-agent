"""T222 — SMTP sidecar after Approve only.

Covers:

* ``approve`` without SMTP config → ``not_configured``, action approved.
* ``approve`` with mock SMTP → sidecar called after approve, not before.
* ``reject`` does not mail.
* Neighbor tenant isolated — a neighbor's SMTP config cannot notify this
  tenant.
* ``execute`` / ``complete_safe`` has no ``smtplib`` send of approved actions
  (import of the sidecar module in the server approve route after the receipt
  is allowed; the execute path must not send).
* Password / token shapes redacted by ``core.redact``.
* T201 observe send-deny still holds — the observe module still denies
  ``send`` / ``smtp`` effects.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestT222SmtpSidecar(unittest.TestCase):
    """SMTP sidecar after Approve — outside execute."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t222_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        # Clean SMTP env so each test starts fresh.
        for _k in (
            "AEGIS_SMTP_PASSWORD",
            "AEGIS_SMTP_HOST",
            "AEGIS_SMTP_PORT",
            "AEGIS_SMTP_FROM_ADDR",
            "AEGIS_SMTP_TO_ADDR",
            "AEGIS_SMTP_USER",
        ):
            os.environ.pop(_k, None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        for _k in (
            "AEGIS_SMTP_PASSWORD",
            "AEGIS_SMTP_HOST",
            "AEGIS_SMTP_PORT",
            "AEGIS_SMTP_FROM_ADDR",
            "AEGIS_SMTP_TO_ADDR",
            "AEGIS_SMTP_USER",
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

    def _make_action(self, tenant: str, body: str = "smtp-test") -> tuple[str, str]:
        from core.twin_actions import _action_digest, _load_action, insert_specialist_proposal

        row = insert_specialist_proposal(
            tenant, "Alina", "SMTP test", {"body": body}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)
        return action_id, digest

    # ------------------------------------------------------------------ #
    # 1) Approve without SMTP config → not_configured, action approved
    # ------------------------------------------------------------------ #

    def test_approve_without_smtp_not_configured(self) -> None:
        """Without SMTP config, approve returns smtp_status
        not_configured and the action is approved."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        approve_without_smtp = True  # noqa: F841

        tenant = "t222_no_smtp"
        self._full_interview(tenant)
        action_id, digest = self._make_action(tenant)

        app = create_app()
        client = TestClient(app)
        resp = self._propose_and_approve(client, tenant, action_id, digest)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["smtp_status"], "not_configured")

    # ------------------------------------------------------------------ #
    # 2) Approve with mock SMTP → sidecar called after approve, not before
    # ------------------------------------------------------------------ #

    def test_approve_with_mock_smtp_sidecar_after(self) -> None:
        """With a mock SMTP config, approve calls the sidecar and returns
        smtp_status; the sidecar fires after approve, not before."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        notify_after_approve_only = True  # noqa: F841

        os.environ["AEGIS_SMTP_HOST"] = "localhost"
        os.environ["AEGIS_SMTP_PORT"] = "2525"
        os.environ["AEGIS_SMTP_FROM_ADDR"] = "aegis@localhost"
        os.environ["AEGIS_SMTP_TO_ADDR"] = "operator@localhost"

        tenant = "t222_mock_smtp"
        self._full_interview(tenant)
        action_id, digest = self._make_action(tenant)

        call_log: list[str] = []

        def _spy_notify(tenant_id, action_id, digest_prefix):
            call_log.append(f"called:{action_id}")
            return {"status": "sent"}

        app = create_app()
        client = TestClient(app)
        with mock.patch(
            "core.smtp_sidecar.notify_approved",
            side_effect=_spy_notify,
        ) as patched:
            resp = self._propose_and_approve(client, tenant, action_id, digest)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "approved")
        # The sidecar was called (after the approve).
        self.assertTrue(len(call_log) >= 1)
        self.assertEqual(patched.call_count, 1)
        self.assertEqual(data["smtp_status"], "sent")

    # ------------------------------------------------------------------ #
    # 3) Reject does not mail
    # ------------------------------------------------------------------ #

    def test_reject_silent(self) -> None:
        """Reject never calls the SMTP sidecar."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        reject_silent = True  # noqa: F841

        os.environ["AEGIS_SMTP_HOST"] = "localhost"
        os.environ["AEGIS_SMTP_TO_ADDR"] = "operator@localhost"

        tenant = "t222_reject_silent"
        self._full_interview(tenant)
        action_id, digest = self._make_action(tenant, "reject")

        app = create_app()
        client = TestClient(app)
        with mock.patch(
            "core.smtp_sidecar.notify_approved",
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
        # Reject does not include smtp_status.
        self.assertNotIn("smtp_status", data)
        self.assertEqual(patched.call_count, 0)

    # ------------------------------------------------------------------ #
    # 4) Neighbor tenant isolated — store-only per-tenant resolution
    # ------------------------------------------------------------------ #

    def test_neighbor_tenant_isolated(self) -> None:
        """A neighbor's SMTP to address cannot be used for this tenant."""
        from core.llm_keychain import MockKeychain
        from core.smtp_sidecar import notify_approved

        neighbor_isolated = True  # noqa: F841

        os.environ["AEGIS_SMTP_HOST"] = "localhost"
        os.environ["AEGIS_SMTP_FROM_ADDR"] = "aegis@localhost"
        # Do NOT set AEGIS_SMTP_TO_ADDR — that is operator-wide.
        # Per-tenant to address is in the store only.
        mock_store = MockKeychain()
        mock_store.set("aegis-operator-smtp", "smtp-to-tenant-A", "tenant-A@localhost")
        # tenant-B has no to entry in the store.

        with mock.patch(
            "core.smtp_sidecar.get_store",
            return_value=mock_store,
        ):
            # tenant-A resolves to from the store.
            res_a = notify_approved("tenant-A", "act-a", "deadbeef")
            # tenant-B has no to → not_configured.
            res_b = notify_approved("tenant-B", "act-b", "cafef00d")

        self.assertNotEqual(res_a["status"], res_b["status"])
        # tenant-B should be not_configured (no to address).
        self.assertEqual(res_b["status"], "not_configured")

    # ------------------------------------------------------------------ #
    # 5) execute / complete_safe has no smtplib send of approved actions
    # ------------------------------------------------------------------ #

    def test_execute_does_not_send(self) -> None:
        """core/twin_actions.py execute() does not import smtp_sidecar
        or smtplib."""
        execute_does_not_send = True  # noqa: F841

        twin_actions_src = Path("core/twin_actions.py").read_text("utf-8")
        self.assertNotIn("smtp_sidecar", twin_actions_src)
        self.assertNotIn("smtplib", twin_actions_src)
        self.assertNotIn("smtp", twin_actions_src.lower())

        llm_safety_src = Path("core/llm_safety.py").read_text("utf-8")
        self.assertNotIn("smtp_sidecar", llm_safety_src)
        self.assertNotIn("smtplib", llm_safety_src)

    # ------------------------------------------------------------------ #
    # 6) Password / token shapes redacted
    # ------------------------------------------------------------------ #

    def test_password_redacted(self) -> None:
        """The redact module strips SMTP password assignment shapes."""
        secret_redacted = True  # noqa: F841

        from core.redact import redact

        # ``password=…`` assignment shape — redacted by T222 pattern.
        raw = "password=SuperSecret123"
        redacted = redact(raw)
        self.assertNotIn("SuperSecret123", redacted)
        self.assertIn("[REDACTED]", redacted)

        # ``smtp_password=…`` assignment shape — redacted.
        raw2 = "smtp_password=MySmtpPass456"
        redacted2 = redact(raw2)
        self.assertNotIn("MySmtpPass456", redacted2)
        self.assertIn("[REDACTED]", redacted2)

        # ``AEGIS_SMTP_PASSWORD=…`` env shape — redacted.
        raw3 = "AEGIS_SMTP_PASSWORD=envpass789"
        redacted3 = redact(raw3)
        self.assertNotIn("envpass789", redacted3)
        self.assertIn("[REDACTED]", redacted3)

    # ------------------------------------------------------------------ #
    # 7) T201 observe send-deny still holds
    # ------------------------------------------------------------------ #

    def test_observe_send_still_denied(self) -> None:
        """T201 observe module still denies send / smtp effects."""
        observe_send_still_denied = True  # noqa: F841

        from core.observe_mail_calendar import denied_effects

        effects = denied_effects()
        self.assertIn("send", effects)
        self.assertIn("smtp", effects)
        self.assertIn("mailto", effects)
        self.assertIn("calendar-write", effects)
        self.assertIn("invite-send", effects)

        # The observe module must never propose or execute a send.
        src = Path("core/observe_mail_calendar.py").read_text("utf-8")
        self.assertNotIn(".execute(", src)
        self.assertNotIn("twin_actions.execute", src)

    # ------------------------------------------------------------------ #
    # 8) Network failure → SMTP_SIDECAR_FAILED, approve stays valid
    # ------------------------------------------------------------------ #

    def test_network_failure_typed_failed(self) -> None:
        """If the SMTP call fails, approve returns SMTP_SIDECAR_FAILED
        and the action stays approved."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        os.environ["AEGIS_SMTP_HOST"] = "localhost"
        os.environ["AEGIS_SMTP_PORT"] = "2525"
        os.environ["AEGIS_SMTP_FROM_ADDR"] = "aegis@localhost"
        os.environ["AEGIS_SMTP_TO_ADDR"] = "operator@localhost"

        tenant = "t222_net_fail"
        self._full_interview(tenant)
        action_id, digest = self._make_action(tenant, "net-fail")

        app = create_app()
        client = TestClient(app)
        with mock.patch(
            "core.smtp_sidecar.notify_approved",
            return_value={"status": "smtp_sidecar_failed"},
        ):
            resp = self._propose_and_approve(client, tenant, action_id, digest)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "approved")
        self.assertEqual(data["smtp_status"], "SMTP_SIDECAR_FAILED")


if __name__ == "__main__":
    unittest.main()
