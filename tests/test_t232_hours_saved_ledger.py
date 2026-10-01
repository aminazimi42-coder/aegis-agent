"""T232 — Hours saved from the local decision ledger only.

Covers:

* ``test_same_tenant_count_matches_approved_rows`` — the hours_saved
  count matches the number of approved rows in the ledger window.
* ``test_neighbor_tenant_is_zero`` — a neighbor tenant returns zero
  hours; it never counts another tenant's rows.
* ``test_forget_clears_count`` — Forget clears the count for that
  tenant; hours_saved returns zero after Forget.
* ``test_missing_ledger_is_zero`` — a tenant with no ledger rows
  returns zero hours, not an error.
* ``test_no_stripe_in_core`` — no live Stripe secret token in ``core/``.
* ``test_readme_and_status_no_two_week_or_multi_month`` — README and
  STATUS do not contain ``two-week`` or ``multi-month`` as a shipped
  claim for T232.
* ``test_status_has_t232_line`` — STATUS.md has a ``T232`` line.
* ``test_hours_saved_does_not_unlock_execute`` — the hours_saved
  number does not unlock execute and does not change entitlement.
* ``test_decision_ledger_route_returns_hours_saved`` — the existing
  decision-ledger GET route returns the hours_saved read.
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


class TestT232HoursSaved(unittest.TestCase):
    """Hours saved from the local decision ledger only."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t232_")
        self._prev_env = os.environ.get("AEGIS_DATA_DIR")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        if self._prev_env is not None:
            os.environ["AEGIS_DATA_DIR"] = self._prev_env
        else:
            os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) same-tenant count matches approved rows
    # ------------------------------------------------------------------ #
    def test_same_tenant_count_matches_approved_rows(self) -> None:
        """hours_saved count matches the number of approved rows."""
        tenant = "t232-same"
        # Append 3 approve rows and 2 reject rows.
        for i in range(3):
            decision_ledger.append(
                tenant,
                {
                    "action_id": f"act-approve-{i}",
                    "specialist": "Alina",
                    "decision": "approve",
                },
            )
        for i in range(2):
            decision_ledger.append(
                tenant,
                {
                    "action_id": f"act-reject-{i}",
                    "specialist": "Kian",
                    "decision": "reject",
                },
            )
        result = decision_ledger.hours_saved(tenant)
        # 3 approved * 15 min = 45 min = 0.75 hours
        self.assertEqual(result["approved_count"], 3)
        self.assertEqual(result["hours_saved"], 0.75)
        self.assertEqual(result["label"], "local ledger count")
        self.assertEqual(result["tenant_id"], tenant)

    # ------------------------------------------------------------------ #
    # 2) neighbor tenant is zero
    # ------------------------------------------------------------------ #
    def test_neighbor_tenant_is_zero(self) -> None:
        """A neighbor tenant returns zero hours; never cross-tenant rows."""
        tenant_a = "t232-neighbor-a"
        tenant_b = "t232-neighbor-b"
        for i in range(4):
            decision_ledger.append(
                tenant_a,
                {
                    "action_id": f"act-a-{i}",
                    "specialist": "Alina",
                    "decision": "approve",
                },
            )
        result_b = decision_ledger.hours_saved(tenant_b)
        self.assertEqual(result_b["approved_count"], 0)
        self.assertEqual(result_b["hours_saved"], 0)
        result_a = decision_ledger.hours_saved(tenant_a)
        self.assertEqual(result_a["approved_count"], 4)

    # ------------------------------------------------------------------ #
    # 3) Forget clears the count
    # ------------------------------------------------------------------ #
    def test_forget_clears_count(self) -> None:
        """Forget clears the count; hours_saved returns zero after Forget."""
        tenant = "t232-forget"
        for i in range(3):
            decision_ledger.append(
                tenant,
                {
                    "action_id": f"act-f-{i}",
                    "specialist": "Alina",
                    "decision": "approve",
                },
            )
        result_before = decision_ledger.hours_saved(tenant)
        self.assertEqual(result_before["approved_count"], 3)
        decision_ledger.forget(tenant)
        result_after = decision_ledger.hours_saved(tenant)
        self.assertEqual(result_after["approved_count"], 0)
        self.assertEqual(result_after["hours_saved"], 0)

    # ------------------------------------------------------------------ #
    # 4) missing ledger is zero, not an error
    # ------------------------------------------------------------------ #
    def test_missing_ledger_is_zero(self) -> None:
        """A tenant with no ledger rows returns zero, not an error."""
        tenant = "t232-missing"
        result = decision_ledger.hours_saved(tenant)
        self.assertEqual(result["approved_count"], 0)
        self.assertEqual(result["hours_saved"], 0)
        self.assertEqual(result["label"], "local ledger count")

    # ------------------------------------------------------------------ #
    # 5) no stripe in core
    # ------------------------------------------------------------------ #
    def test_no_stripe_in_core(self) -> None:
        """No live Stripe secret token in ``core/``."""
        core_dir = _REPO_ROOT / "core"
        pattern = re.compile(r"sk_live_[A-Za-z0-9]{24,}")
        offenders: list[str] = []
        for py in core_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="ignore")
            for m in pattern.finditer(text):
                offenders.append(f"{py.name}: {m.group()}")
        self.assertEqual(offenders, [], f"Stripe live token in core/: {offenders}")

    # ------------------------------------------------------------------ #
    # 6) README and STATUS do not contain two-week or multi-month
    # ------------------------------------------------------------------ #
    def test_readme_and_status_no_two_week_or_multi_month(self) -> None:
        """README has no two-week or multi-month as a shipped claim."""
        readme = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn("two-week", readme)
        self.assertNotIn("two week", readme)

    # ------------------------------------------------------------------ #
    # 7) STATUS has T232 line
    # ------------------------------------------------------------------ #
    def test_status_has_t232_line(self) -> None:
        """STATUS.md contains ``T232``."""
        text = _STATUS.read_text(encoding="utf-8")
        self.assertIn("T232", text)

    # ------------------------------------------------------------------ #
    # 8) hours_saved does not unlock execute or change entitlement
    # ------------------------------------------------------------------ #
    def test_hours_saved_does_not_unlock_execute(self) -> None:
        """The hours_saved number does not unlock execute or change
        entitlement; a proposed (not approved) action still raises
        PermissionError, and the entitlement tier stays echo."""
        tenant = "t232-no-unlock"
        _seed_profile(tenant)
        app = create_app()
        client = TestClient(app)
        # Propose via the operator endpoint.
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json().get("proposals", [])
        self.assertGreater(len(proposals), 0)
        # Pick a proposed (not-yet-approved) action — it is still
        # in ``proposed`` status so execute must raise PermissionError.
        proposed_action_id = proposals[0]["action_id"]
        # Approve a *different* action so the ledger has a row.
        second_proposal = proposals[1] if len(proposals) > 1 else proposals[0]
        action_id = second_proposal["action_id"]
        digest = second_proposal.get("payload_sha256", "")
        resp2 = client.post(
            f"/api/v1/twin/actions/{action_id}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": digest,
            },
        )
        self.assertEqual(resp2.status_code, 200)
        # hours_saved is positive now.
        hs = decision_ledger.hours_saved(tenant)
        self.assertGreater(hs["hours_saved"], 0)
        # But the still-proposed action still raises PermissionError —
        # hours_saved does not unlock execute.
        from core.twin_actions import execute

        with self.assertRaises(PermissionError):
            execute(proposed_action_id, tenant_id=tenant)
        # Entitlement tier is unchanged — still echo (default) regardless
        # of hours_saved.
        from core.entitlement import current_tier

        tier_before = current_tier()
        self.assertEqual(tier_before, "echo")

    # ------------------------------------------------------------------ #
    # 9) decision-ledger route returns hours_saved
    # ------------------------------------------------------------------ #
    def test_decision_ledger_route_returns_hours_saved(self) -> None:
        """The existing decision-ledger GET route returns the hours_saved
        read for the caller tenant only."""
        tenant = "t232-route"
        _seed_profile(tenant)
        app = create_app()
        client = TestClient(app)
        # Propose + approve so the ledger has a row.
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json().get("proposals", [])
        self.assertGreater(len(proposals), 0)
        action_id = proposals[0]["action_id"]
        digest = proposals[0].get("payload_sha256", "")
        resp2 = client.post(
            f"/api/v1/twin/actions/{action_id}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": digest,
            },
        )
        self.assertEqual(resp2.status_code, 200)
        # The decision-ledger GET route returns hours_saved.
        resp3 = client.get(f"/api/v1/twin/decision-ledger/{tenant}")
        self.assertEqual(resp3.status_code, 200)
        body = resp3.json()
        self.assertIn("hours_saved", body)
        self.assertEqual(body["hours_saved"]["label"], "local ledger count")
        self.assertGreater(body["hours_saved"]["hours_saved"], 0)
        # A neighbor tenant returns zero.
        resp4 = client.get("/api/v1/twin/decision-ledger/t232-route-neighbor")
        self.assertEqual(resp4.status_code, 200)
        body4 = resp4.json()
        self.assertEqual(body4["hours_saved"]["hours_saved"], 0)


if __name__ == "__main__":
    unittest.main()
