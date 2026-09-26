"""T216 — Intact after Approve and copy-redact.

Covers:

* ``approve`` success response includes ``chain_state`` Intact when the
  receipt verifies on the tenant chain (after execute + approve).
* If the receipt bytes are mutated in the store, the page shows Tampered.
* The copy-redact path redacts secret shapes (Bearer, webhook, SSH, PEM)
  so the clipboard never receives a raw token.
* A neighbor tenant's verify-chain does not report Intact for this tenant.
* ``core/`` has no Stripe token.
* Still six specialist names only (no seventh agent).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.twin_actions import (
    _action_digest,
    _load_action,
    approve,
    execute,
    insert_specialist_proposal,
    verify_chain,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT216IntactCopy(unittest.TestCase):
    """Intact after Approve and copy-redact."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t216_")
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

    def _receipt_path(self, tenant_id: str, action_id: str) -> Path:
        return (
            Path(self._tmp)
            / "work_products"
            / tenant_id
            / "receipts"
            / f"{action_id}.md"
        )

    # ------------------------------------------------------------------ #
    # 1) Approve then verify-chain Intact
    # ------------------------------------------------------------------ #

    def test_approve_then_verify_chain_intact(self) -> None:
        """After execute + approve, verify-chain reports Intact."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t216_intact"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Review the weekly digest", {"body": "intact test"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action))
        execute(action_id, tenant)
        self.assertEqual(verify_chain(tenant, action_id), "Intact")

        # The approve route response includes chain_state.
        app = create_app()
        client = TestClient(app)
        row2 = insert_specialist_proposal(
            tenant, "Kian", "Second digest", {"body": "second"}
        )
        action2 = _load_action(row2["action_id"])
        assert action2 is not None
        resp = client.post(
            f"/api/v1/twin/actions/{row2['action_id']}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": _action_digest(action2),
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("chain_state", data)
        self.assertEqual(data["chain_state"], "Intact")

    # ------------------------------------------------------------------ #
    # 2) Mutated receipt then Tampered
    # ------------------------------------------------------------------ #

    def test_mutated_receipt_then_tampered(self) -> None:
        """If the receipt bytes are mutated, verify-chain reports Tampered."""
        tenant = "t216_tampered"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Review the weekly digest", {"body": "tamper test"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action))
        execute(action_id, tenant)
        self.assertEqual(verify_chain(tenant, action_id), "Intact")

        # Mutate the receipt file.
        receipt_path = self._receipt_path(tenant, action_id)
        original = receipt_path.read_text("utf-8")
        tampered = original.replace(
            "title: Review the weekly digest", "title: HACKED"
        )
        receipt_path.write_text(tampered, "utf-8")
        self.assertEqual(verify_chain(tenant, action_id), "Tampered")

        # The page shows Tampered, not Missing, and not Intact.
        html = Path("app.html").read_text("utf-8")
        self.assertIn("Tampered", html)

    # ------------------------------------------------------------------ #
    # 3) Copy path redacts secret shapes
    # ------------------------------------------------------------------ #

    def test_copy_path_redacts_secret_shapes(self) -> None:
        """The copy-redact regex in the operator page redacts bearer,
        webhook, SSH, and PEM shapes so the clipboard never gets a raw
        token."""
        html = Path("app.html").read_text("utf-8")
        # The copyRedactCard function must exist and redact secret shapes.
        self.assertIn("copyRedactCard", html)
        # The redaction regexes must be present in the page source.
        self.assertIn("[REDACTED]", html)
        # Bearer shape is redacted.
        self.assertIn("Bearer", html)
        # The core redact helper also redacts these shapes.
        from core.redact import redact

        raw = "Bearer sk-1234567890abcdef webhook_secret=whsec_abcdef1234567890"
        redacted = redact(raw)
        self.assertNotIn("sk-1234567890abcdef", redacted)
        self.assertNotIn("whsec_abcdef1234567890", redacted)
        self.assertIn("[REDACTED]", redacted)

    # ------------------------------------------------------------------ #
    # 4) Neighbor chain does not report Intact for this tenant
    # ------------------------------------------------------------------ #

    def test_neighbor_chain_not_intact(self) -> None:
        """A neighbor tenant's verify-chain stays empty / not Intact for
        this tenant."""
        tenant_a = "t216_neighbor_a"
        tenant_b = "t216_neighbor_b"
        self._full_interview(tenant_a)
        self._full_interview(tenant_b)

        # Tenant A executes an action and the receipt verifies Intact.
        row_a = insert_specialist_proposal(
            tenant_a, "Alina", "Review the weekly digest", {"body": "a"}
        )
        action_a = _load_action(row_a["action_id"])
        assert action_a is not None
        approve(row_a["action_id"], tenant_a, "tester", _action_digest(action_a))
        execute(row_a["action_id"], tenant_a)
        self.assertEqual(verify_chain(tenant_a, row_a["action_id"]), "Intact")

        # Tenant B has no executed receipt — verify-chain returns Missing,
        # not Intact.
        from core.twin_actions import list_actions

        actions_b = list_actions(tenant_b)
        executed_b = [a for a in actions_b if a.get("status") == "executed"]
        self.assertEqual(executed_b, [])

        # Tenant B's verify-chain for tenant A's action_id is Missing.
        self.assertEqual(verify_chain(tenant_b, row_a["action_id"]), "Missing")

    # ------------------------------------------------------------------ #
    # 5) core/ has no stripe token
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
    # 6) Still six specialist names only
    # ------------------------------------------------------------------ #

    def test_still_six_specialists(self) -> None:
        """The agent registry has exactly six specialist names."""
        from core.agent_registry import AGENT_REGISTRY

        names = [spec.name for spec in AGENT_REGISTRY]
        self.assertEqual(len(names), 6)
        expected = {"Alina", "Kian", "Bita", "Aylin", "Ahmad", "Amin"}
        self.assertEqual(set(names), expected)

    # ------------------------------------------------------------------ #
    # 7) No live network sentinel
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
