"""T211 — Tenant-bound local decision ledger.

Covers:

* ``test_append_list_same_tenant`` — append and list for one tenant.
* ``test_neighbor_tenant_cannot_list`` — a neighbor tenant sees an empty
  list; it never reads another tenant's rows.
* ``test_forget_drops_only_that_tenant`` — forget removes only the
  caller's rows; neighbor rows stay.
* ``test_approve_route_appends_row`` — the approve API route appends one
  row to the ledger.
* ``test_reject_route_appends_row`` — the reject API route appends one
  row to the ledger.
* ``test_readme_mentions_decision_ledger`` — the README mentions the
  decision ledger or tenant-bound ledger.
* ``test_readme_does_not_claim_two_week`` — the README has no
  ``two-week`` or ``two week``.
* ``test_status_has_t211_line`` — STATUS.md has a ``T211`` line.
* ``test_core_tree_has_no_stripe_token`` — no live Stripe secret token
  in ``core/``.

No xfail.  No live ``$HOME/.aegis`` writes; ``tmp_path`` is the data dir.
No uvicorn, no network, no hit to aegis-agent-haka.
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from app.server import create_app
from core import decision_ledger
from core.twin_interview import answer, commit, start_session
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"
_STATUS = _REPO_ROOT / "STATUS.md"

_QUESTION_IDS = (
    "q_role",
    "q_decision_style",
    "q_tools",
    "q_risk",
    "q_ethics",
    "q_repos",
)


def _seed_profile(tenant: str) -> None:
    """Start, answer all six questions, and commit a profile for *tenant*."""
    session = start_session(tenant)
    sid = session["session_id"]
    for q_id in _QUESTION_IDS:
        answer(sid, q_id, "test answer")
    commit(sid, consent=True)


class TestT211DecisionLedger(unittest.TestCase):
    """Tenant-bound local decision ledger on approve/reject."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t211_")
        self._prev_env = os.environ.get("AEGIS_DATA_DIR")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        if self._prev_env is not None:
            os.environ["AEGIS_DATA_DIR"] = self._prev_env
        else:
            os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) append + list same tenant
    # ------------------------------------------------------------------ #
    def test_append_list_same_tenant(self) -> None:
        """Append two rows for one tenant and list them newest last."""
        tenant = "t211-same"
        decision_ledger.append(
            tenant,
            {
                "action_id": "act-aaa",
                "specialist": "Alina",
                "decision": "approve",
                "reason_code": "",
                "digest_prefix": "abc123",
            },
        )
        decision_ledger.append(
            tenant,
            {
                "action_id": "act-bbb",
                "specialist": "Kian",
                "decision": "reject",
                "reason_code": "DUPLICATE",
                "digest_prefix": "def456",
            },
        )
        rows = decision_ledger.list(tenant)
        self.assertEqual(len(rows), 2)
        # Newest last (insertion order).
        self.assertEqual(rows[0]["action_id"], "act-aaa")
        self.assertEqual(rows[0]["decision"], "approve")
        self.assertEqual(rows[1]["action_id"], "act-bbb")
        self.assertEqual(rows[1]["decision"], "reject")
        self.assertEqual(rows[1]["reason_code"], "DUPLICATE")

    # ------------------------------------------------------------------ #
    # 2) neighbor tenant cannot list
    # ------------------------------------------------------------------ #
    def test_neighbor_tenant_cannot_list(self) -> None:
        """A neighbor tenant sees an empty list — never cross-tenant rows."""
        tenant_a = "t211-neighbor-a"
        tenant_b = "t211-neighbor-b"
        decision_ledger.append(
            tenant_a,
            {
                "action_id": "act-aaa",
                "specialist": "Alina",
                "decision": "approve",
            },
        )
        rows_b = decision_ledger.list(tenant_b)
        self.assertEqual(rows_b, [])
        rows_a = decision_ledger.list(tenant_a)
        self.assertEqual(len(rows_a), 1)

    # ------------------------------------------------------------------ #
    # 3) forget drops only that tenant
    # ------------------------------------------------------------------ #
    def test_forget_drops_only_that_tenant(self) -> None:
        """Forget removes only the caller's rows; neighbor rows stay."""
        tenant_a = "t211-forget-a"
        tenant_b = "t211-forget-b"
        decision_ledger.append(
            tenant_a,
            {
                "action_id": "act-a1",
                "specialist": "Alina",
                "decision": "approve",
            },
        )
        decision_ledger.append(
            tenant_b,
            {
                "action_id": "act-b1",
                "specialist": "Kian",
                "decision": "reject",
            },
        )
        decision_ledger.forget(tenant_a)
        rows_a = decision_ledger.list(tenant_a)
        self.assertEqual(rows_a, [])
        rows_b = decision_ledger.list(tenant_b)
        self.assertEqual(len(rows_b), 1)
        self.assertEqual(rows_b[0]["action_id"], "act-b1")

    # ------------------------------------------------------------------ #
    # 4) approve route appends row
    # ------------------------------------------------------------------ #
    def test_approve_route_appends_row(self) -> None:
        """The approve API route appends one row to the ledger."""
        tenant = "t211-approve-route"
        _seed_profile(tenant)
        app = create_app()
        client = TestClient(app)
        # Propose via the operator endpoint — it returns payload_sha256.
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json().get("proposals", [])
        self.assertGreater(len(proposals), 0)
        proposal = proposals[0]
        action_id = proposal["action_id"]
        digest = proposal.get("payload_sha256", "")
        self.assertTrue(digest, "propose did not return a payload_sha256")
        # Approve
        resp2 = client.post(
            f"/api/v1/twin/actions/{action_id}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": digest,
            },
        )
        self.assertEqual(resp2.status_code, 200)
        # Ledger has at least one approve row for this action.
        rows = decision_ledger.list(tenant)
        self.assertGreaterEqual(len(rows), 1)
        approve_rows = [r for r in rows if r["decision"] == "approve"]
        self.assertGreater(len(approve_rows), 0)
        self.assertEqual(approve_rows[0]["action_id"], action_id)

    # ------------------------------------------------------------------ #
    # 5) reject route appends row
    # ------------------------------------------------------------------ #
    def test_reject_route_appends_row(self) -> None:
        """The reject API route appends one row to the ledger."""
        tenant = "t211-reject-route"
        _seed_profile(tenant)
        app = create_app()
        client = TestClient(app)
        # Propose via the operator endpoint — it returns payload_sha256.
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json().get("proposals", [])
        self.assertGreater(len(proposals), 0)
        proposal = proposals[0]
        action_id = proposal["action_id"]
        # Reject — empty expected_payload_sha256 skips the digest check.
        resp2 = client.post(
            f"/api/v1/twin/actions/{action_id}/reject",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "reason_enum": "DUPLICATE",
            },
        )
        self.assertEqual(resp2.status_code, 200)
        # Ledger has at least one reject row for this action.
        rows = decision_ledger.list(tenant)
        self.assertGreaterEqual(len(rows), 1)
        reject_rows = [r for r in rows if r["decision"] == "reject"]
        self.assertGreater(len(reject_rows), 0)
        self.assertEqual(reject_rows[0]["action_id"], action_id)

    # ------------------------------------------------------------------ #
    # 6) README mentions decision ledger
    # ------------------------------------------------------------------ #
    def test_readme_mentions_decision_ledger(self) -> None:
        """The README mentions the decision ledger or tenant-bound ledger."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertTrue(
            "decision ledger" in text or "tenant-bound" in text,
            "README does not mention decision ledger or tenant-bound",
        )

    # ------------------------------------------------------------------ #
    # 7) README does not claim two week
    # ------------------------------------------------------------------ #
    def test_readme_does_not_claim_two_week(self) -> None:
        """The README has no ``two-week`` or ``two week``."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn("two-week", text)
        self.assertNotIn("two week", text)

    # ------------------------------------------------------------------ #
    # 8) STATUS has T211 line
    # ------------------------------------------------------------------ #
    def test_status_has_t211_line(self) -> None:
        """STATUS.md contains ``T211``."""
        text = _STATUS.read_text(encoding="utf-8")
        self.assertIn("T211", text)

    # ------------------------------------------------------------------ #
    # 9) core/ has no Stripe token
    # ------------------------------------------------------------------ #
    def test_core_tree_has_no_stripe_token(self) -> None:
        """No live Stripe secret token (``sk_live_`` + 24+ chars) in ``core/``."""
        core_dir = _REPO_ROOT / "core"
        pattern = re.compile(r"sk_live_[A-Za-z0-9]{24,}")
        offenders: list[str] = []
        for py in core_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="ignore")
            for m in pattern.finditer(text):
                offenders.append(f"{py.name}: {m.group()}")
        self.assertEqual(offenders, [], f"Stripe live token in core/: {offenders}")


if __name__ == "__main__":
    unittest.main()
