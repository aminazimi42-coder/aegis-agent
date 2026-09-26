"""T225 — session evidence zip + Intact immediately after Approve.

Covers:

* One operator click (API call) writes a local session evidence zip under
  ``AEGIS_DATA_DIR/{tenant}/export/``.  The zip lists the last signed brief
  and its sibling ``.sig`` when present.
* After Approve, the approved card shows Intact (clean chain) in the same
  turn — the approve route response includes ``chain_state``.
* A mutated receipt → Tampered on the card.
* Neighbor tenant zip is empty or 404 for this tenant (no cross-tenant
  leakage).
* ``forget_all`` drops that tenant's export zip.
* ``core/`` has no Stripe token.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
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


class TestT225SessionZip(unittest.TestCase):
    """Session evidence zip + Intact immediately after Approve."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t225_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _full_interview(self, tenant_id: str) -> str:
        """Run a complete interview and return the session id."""
        session = start_session(tenant_id)
        sid = session["session_id"]
        for q in QUESTIONS:
            answer(sid, q["id"], f"ans-{q['id']}")
        commit(sid, True)
        return sid

    def _execute_one_action(self, tenant_id: str) -> str:
        """Propose, approve, and execute one action; return action_id."""
        self._full_interview(tenant_id)
        row = insert_specialist_proposal(
            tenant_id, "Alina", "Review the weekly digest", {"body": "t225"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant_id, "tester", _action_digest(action))
        execute(action_id, tenant_id)
        return action_id

    def _receipt_path(self, tenant_id: str, action_id: str) -> Path:
        return (
            Path(self._tmp)
            / "work_products"
            / tenant_id
            / "receipts"
            / f"{action_id}.md"
        )

    # ------------------------------------------------------------------ #
    # 1) zip exists after click and lists brief+.sig
    # ------------------------------------------------------------------ #

    def test_zip_exists_after_click_and_lists_brief_sig(self) -> None:
        """build_session_zip writes a zip under {tenant}/export/ containing
        the signed brief and its .sig sibling."""
        from core.evidence_desk import build_session_zip
        from core.twin_local_recall import signed_export

        tenant = "t225_zip"
        self._execute_one_action(tenant)
        # Write a signed brief so it exists under export/.
        signed_export(tenant, name="local_t225_test.md")
        result = build_session_zip(tenant)

        zip_path = Path(result["path"])
        self.assertTrue(zip_path.is_file(), f"zip missing at {zip_path}")
        self.assertTrue(zip_path.suffix == ".zip")
        # The zip lives under {tenant}/export/.
        self.assertIn("t225_zip", str(zip_path))
        self.assertIn("export", str(zip_path))
        self.assertTrue(result["sha256"])
        self.assertEqual(len(result["sha256"]), 64)

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            # brief.md and brief.md.sig are in the zip.
            self.assertIn("brief.md", names)
            self.assertIn("brief.md.sig", names)
            # verify_chain result is in the zip.
            self.assertIn("verify_chain.txt", names)
            vc = zf.read("verify_chain.txt").decode("utf-8")
            self.assertIn("verify_chain:", vc)
            self.assertIn("tenant_id: " + tenant, vc)
            # receipt_digest is in the zip.
            self.assertIn("receipt_digest.txt", names)
            rd = zf.read("receipt_digest.txt").decode("utf-8")
            self.assertIn("last_receipt_digest:", rd)

    # ------------------------------------------------------------------ #
    # 2) Approve paints Intact on the card
    # ------------------------------------------------------------------ #

    def test_approve_paints_intact_on_card(self) -> None:
        """After execute + approve, the approve route response includes
        chain_state Intact."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t225_intact"
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

        # The approve route response includes chain_state for a second action.
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
        # The latest executed receipt is Intact.
        self.assertEqual(data["chain_state"], "Intact")

        # The operator page HTML shows Intact and Tampered labels.
        html = Path("app.html").read_text("utf-8")
        self.assertIn("Intact", html)

    # ------------------------------------------------------------------ #
    # 3) Mutated receipt Tampered
    # ------------------------------------------------------------------ #

    def test_mutated_receipt_tampered(self) -> None:
        """If the receipt bytes are mutated, the approve route returns
        chain_state Tampered and verify_chain reports Tampered."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t225_tampered"
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

        # The approve route on a second action returns chain_state Tampered.
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
        self.assertEqual(data["chain_state"], "Tampered")

        # The operator page HTML shows Tampered.
        html = Path("app.html").read_text("utf-8")
        self.assertIn("Tampered", html)

    # ------------------------------------------------------------------ #
    # 4) Neighbor isolated
    # ------------------------------------------------------------------ #

    def test_neighbor_isolated(self) -> None:
        """A neighbor tenant's session zip does not contain this tenant's
        data, and this tenant's zip does not contain the neighbor's data."""
        from core.evidence_desk import build_session_zip

        tenant_a = "t225_neighbor_a"
        tenant_b = "t225_neighbor_b"
        self._execute_one_action(tenant_a)
        self._execute_one_action(tenant_b)

        result_a = build_session_zip(tenant_a)
        zip_a = Path(result_a["path"])
        with zipfile.ZipFile(zip_a, "r") as zf:
            vc = zf.read("verify_chain.txt").decode("utf-8")
            self.assertIn(tenant_a, vc)
            self.assertNotIn(tenant_b, vc)

        # Tenant B's export dir has its own zip, not tenant A's.
        result_b = build_session_zip(tenant_b)
        zip_b = Path(result_b["path"])
        self.assertNotEqual(zip_a, zip_b)
        # Tenant A's zip path is under tenant A's export dir.
        self.assertIn(tenant_a, str(zip_a))
        self.assertIn(tenant_b, str(zip_b))

    # ------------------------------------------------------------------ #
    # 5) Forget drops zip
    # ------------------------------------------------------------------ #

    def test_forget_drops_zip(self) -> None:
        """forget_all removes the tenant's export directory (and the zip)."""
        from core.evidence_desk import build_session_zip
        from core.twin_memory_control import forget_all

        tenant = "t225_forget"
        self._execute_one_action(tenant)
        result = build_session_zip(tenant)
        zip_path = Path(result["path"])
        self.assertTrue(zip_path.is_file())

        export_dir = zip_path.parent
        forget_all(tenant)
        self.assertFalse(
            export_dir.exists(),
            "export dir still exists after forget",
        )

    # ------------------------------------------------------------------ #
    # 6) no stripe token in core/
    # ------------------------------------------------------------------ #

    def test_no_stripe_in_core(self) -> None:
        """No file under core/ contains the substring 'stripe'."""
        core_dir = Path("core")
        for p in core_dir.glob("*.py"):
            text = p.read_text("utf-8")
            self.assertNotRegex(
                text,
                r"(?i)stripe",
                f"'stripe' found in {p}",
            )


if __name__ == "__main__":
    unittest.main()
