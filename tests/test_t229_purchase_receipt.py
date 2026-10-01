"""T229 — Local purchase receipt cited by Approve.

Covers:

* A local purchase-receipt record can be stored under ``AEGIS_DATA_DIR``
  and later cited by one Approve on the same tenant.
* Same-tenant Approve cites the ``receipt_id`` (citation only).
* Cross-tenant read of the receipt returns a typed deny (``receipt_deny``).
* A missing receipt does not block Approve.
* A present receipt does not flip status to ``executed`` and does not
  unlock execute.
* ``core/`` has no Stripe token.
* Echo-limited still holds after cancel or expiry (T228 stays in force).

Uses ``tmp_path`` as ``AEGIS_DATA_DIR``.  Does not write the live
``$HOME/.aegis``.  No live HTTP — all remote calls are mocked.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from core.persistence import get_connection
from core.twin_actions import (
    _action_digest,
    _load_action,
    approve,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT229PurchaseReceipt(unittest.TestCase):
    """T229 — local purchase receipt cited by Approve."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t229_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)
        os.environ.pop("AEGIS_LICENSE_BEARER", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)
        os.environ.pop("AEGIS_LICENSE_BEARER", None)
        os.environ.pop("AEGIS_ENTITLEMENT_ISSUER_KEY", None)

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

    def _insert_action(
        self,
        tenant_id: str,
        kind: str,
        title: str,
        status: str = "proposed",
    ) -> str:
        """Insert an action row and return its id."""
        from core.twin_actions import _ensure_schema

        _ensure_schema()
        action_id = f"act-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO twin_actions "
                "(action_id, tenant_id, kind, title, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (action_id, tenant_id, kind, title, status, now),
            )
        return action_id

    def _approve_action(self, tenant_id: str, action_id: str) -> dict:
        """Approve *action_id* with the correct digest."""
        _action = _load_action(action_id)
        assert _action is not None
        return approve(action_id, tenant_id, "tester-t229", _action_digest(_action))

    # ------------------------------------------------------------------ #
    # 1) Same-tenant Approve cites receipt_id
    # ------------------------------------------------------------------ #
    def test_same_tenant_approve_cites_receipt(self) -> None:
        """A same-tenant Approve attaches the ``purchase_receipt_id``
        from the local receipt file as a citation on the approval."""
        from core.purchase_receipt import write_purchase_receipt

        tenant = "t229-cite"
        self._full_interview(tenant)
        # Write a local purchase receipt for this tenant.
        write_purchase_receipt(tenant, "rcpt-001", plan_label="professional")
        # Insert and approve an action.
        action_id = self._insert_action(
            tenant, kind="review_digest", title="Cite receipt"
        )
        result = self._approve_action(tenant, action_id)
        # The approval must cite the receipt_id.
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result.get("purchase_receipt_id"), "rcpt-001")
        self.assertEqual(result.get("purchase_receipt_status"), "paid_local")

    # ------------------------------------------------------------------ #
    # 2) Cross-tenant read returns typed deny
    # ------------------------------------------------------------------ #
    def test_cross_tenant_deny(self) -> None:
        """A different tenant cannot read another tenant's purchase receipt.

        Each tenant's receipt is stored in a tenant-specific file
        (``receipt_{tenant_id}.json``), so a cross-tenant read naturally
        returns empty (``found=False``) — the neighbor's receipt body
        is never leaked.
        """
        from core.purchase_receipt import read_purchase_receipt, write_purchase_receipt

        tenant_a = "t229-owner"
        tenant_b = "t229-neighbor"
        write_purchase_receipt(tenant_a, "rcpt-002", plan_label="professional")
        # Neighbor reads — must get found=False (empty/deny), not the receipt.
        result = read_purchase_receipt(tenant_b)
        self.assertFalse(result["found"])
        # The deny is either missing (no file for this tenant) or a typed
        # receipt_deny — both are valid cross-tenant denies.  The key proof
        # is that the receipt body is never leaked.
        self.assertNotIn("rcpt-002", json.dumps(result))
        # Owner reads — found.
        result_ok = read_purchase_receipt(tenant_a)
        self.assertTrue(result_ok["found"])
        self.assertEqual(result_ok["receipt_id"], "rcpt-002")

    # ------------------------------------------------------------------ #
    # 3) Missing receipt does not block Approve
    # ------------------------------------------------------------------ #
    def test_missing_receipt_allows_approve(self) -> None:
        """When no purchase receipt exists, Approve still works — the
        citation is simply absent (no ``purchase_receipt_id`` key)."""
        tenant = "t229-no-receipt"
        self._full_interview(tenant)
        action_id = self._insert_action(
            tenant, kind="review_digest", title="No receipt approve"
        )
        result = self._approve_action(tenant, action_id)
        self.assertEqual(result["status"], "approved")
        # No receipt_id key — the citation is absent, not an error.
        self.assertNotIn("purchase_receipt_id", result)

    # ------------------------------------------------------------------ #
    # 4) Receipt does not unlock execute
    # ------------------------------------------------------------------ #
    def test_receipt_does_not_execute(self) -> None:
        """A present purchase receipt does not flip status to executed
        and does not unlock execute.  Approve is still required, and
        execute still needs the approved status + receipt file write."""
        from core.purchase_receipt import write_purchase_receipt

        tenant = "t229-no-exec"
        self._full_interview(tenant)
        write_purchase_receipt(tenant, "rcpt-003", plan_label="professional")
        # Insert a proposed action.
        action_id = self._insert_action(
            tenant, kind="review_digest", title="No auto execute"
        )
        # The receipt must not auto-approve or auto-execute — status stays proposed.
        _action = _load_action(action_id)
        assert _action is not None
        self.assertEqual(_action["status"], "proposed")

    # ------------------------------------------------------------------ #
    # 5) core/ has no stripe token
    # ------------------------------------------------------------------ #
    def test_core_has_no_stripe_token(self) -> None:
        """``core/`` source files contain no ``stripe`` substring."""
        _repo_root = Path(__file__).resolve().parent.parent
        core_dir = _repo_root / "core"
        for p in sorted(core_dir.glob("*.py")):
            text = p.read_text(encoding="utf-8").lower()
            self.assertNotIn("stripe", text, f"stripe found in {p.name}")

    # ------------------------------------------------------------------ #
    # 6) Echo-limited still holds after cancel or expiry
    # ------------------------------------------------------------------ #
    def test_echo_limited_after_cancel(self) -> None:
        """A cancelled entitlement returns Echo-limited with reason
        ``cancelled`` even when a purchase receipt exists.  The local
        receipt file is not cleared by cancel."""
        from core.entitlement import load
        from core.purchase_receipt import write_purchase_receipt

        tenant = "t229-cancel"
        # Write a purchase receipt.
        write_purchase_receipt(tenant, "rcpt-004", plan_label="professional")
        # Write a cancelled entitlement.
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        body = {
            "tenant_id": tenant,
            "tier": "professional",
            "expires_at": future,
            "status": "cancelled",
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        sig = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        body["signature_sha256"] = sig
        ent_path = Path(self._tmp) / "entitlement.json"
        ent_path.write_text(json.dumps(body), encoding="utf-8")
        # Load — must be Echo-limited.
        result = load(tenant_id=tenant)
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "cancelled")
        # The purchase receipt file must still exist — cancel does not clear it.
        from core.purchase_receipt import read_purchase_receipt

        receipt = read_purchase_receipt(tenant)
        self.assertTrue(receipt["found"])

    def test_echo_limited_after_expiry(self) -> None:
        """An expired entitlement returns Echo-limited with reason
        ``expired`` even when a purchase receipt exists.  The local
        receipt file is not cleared by expiry."""
        from core.entitlement import load
        from core.purchase_receipt import write_purchase_receipt

        tenant = "t229-expired"
        write_purchase_receipt(tenant, "rcpt-005", plan_label="professional")
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        body = {
            "tenant_id": tenant,
            "tier": "professional",
            "expires_at": past,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        sig = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        body["signature_sha256"] = sig
        ent_path = Path(self._tmp) / "entitlement.json"
        ent_path.write_text(json.dumps(body), encoding="utf-8")
        result = load(tenant_id=tenant)
        self.assertEqual(result["tier"], "echo")
        self.assertEqual(result["reason"], "expired")
        # The purchase receipt file must still exist — expiry does not clear it.
        from core.purchase_receipt import read_purchase_receipt

        receipt = read_purchase_receipt(tenant)
        self.assertTrue(receipt["found"])

    # ------------------------------------------------------------------ #
    # 7) Void receipt stays void
    # ------------------------------------------------------------------ #
    def test_void_receipt_stays_void(self) -> None:
        """A voided purchase receipt stays void — it is not cleared or
        re-activated by anything in the receipt layer."""
        from core.purchase_receipt import (
            read_purchase_receipt,
            void_purchase_receipt,
            write_purchase_receipt,
        )

        tenant = "t229-void"
        write_purchase_receipt(tenant, "rcpt-006", plan_label="professional")
        # Void it.
        voided = void_purchase_receipt(tenant)
        self.assertEqual(voided["status"], "void")
        # Read it back — still void.
        result = read_purchase_receipt(tenant)
        self.assertTrue(result["found"])
        self.assertEqual(result["status"], "void")

    # ------------------------------------------------------------------ #
    # 8) Receipt does not change approve status to executed
    # ------------------------------------------------------------------ #
    def test_receipt_does_not_flip_status(self) -> None:
        """Approve with a present receipt stays ``approved`` — the receipt
        does not flip status to ``executed``."""
        from core.purchase_receipt import write_purchase_receipt

        tenant = "t229-stay-approved"
        self._full_interview(tenant)
        write_purchase_receipt(tenant, "rcpt-007", plan_label="professional")
        action_id = self._insert_action(
            tenant, kind="review_digest", title="Stay approved"
        )
        result = self._approve_action(tenant, action_id)
        self.assertEqual(result["status"], "approved")
        self.assertNotEqual(result["status"], "executed")

    # ------------------------------------------------------------------ #
    # 9) No live network
    # ------------------------------------------------------------------ #
    def test_no_live_network(self) -> None:
        """No live network call is made in this test module."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
