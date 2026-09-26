"""T212 — Next-propose from local decision ledger within TTL.

Covers:

* ``test_recent_caps_and_ttl_skips_old`` — recent() caps at n and skips
  rows older than TTL.
* ``test_neighbor_recent_empty`` — a neighbor tenant sees ``[]``.
* ``test_propose_includes_hint_after_approve`` — after an approve the
  next propose response carries a non-empty ``last_decisions_hint``.
* ``test_forget_clears_hint_on_next_propose`` — after Forget the next
  propose response carries an empty hint.
* ``test_no_auto_execute_from_hint`` — a hint on the propose card does
  not cause execution; the action stays ``proposed`` until a separate
  Approve + Execute.
* ``test_readme_mentions_ttl_or_next_propose`` — README mentions TTL or
  next propose.
* ``test_readme_does_not_claim_two_week`` — no two-week or two week.
* ``test_readme_does_not_claim_multi_month_twin`` — no multi-month twin.
* ``test_status_has_t212_line`` — STATUS.md has a ``T212`` line.
* ``test_core_tree_has_no_stripe_token`` — no live Stripe token in core/.

No xfail.  No live ``$HOME/.aegis`` writes; tmp_path is the data dir.
No uvicorn, no network, no hit to aegis-agent-haka.
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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


class TestT212NextProposeTTL(unittest.TestCase):
    """Next-propose hint from local decision ledger within TTL."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t212_")
        self._prev_env = os.environ.get("AEGIS_DATA_DIR")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        if self._prev_env is not None:
            os.environ["AEGIS_DATA_DIR"] = self._prev_env
        else:
            os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1) recent caps and ttl skips old
    # ------------------------------------------------------------------ #
    def test_recent_caps_and_ttl_skips_old(self) -> None:
        """recent() caps at n and skips rows older than ttl_hours."""
        tenant = "t212-recent-cap"
        # Insert one old row (older than ttl) and two fresh rows.
        decision_ledger.append(
            tenant,
            {
                "action_id": "act-old",
                "specialist": "Alina",
                "decision": "approve",
                "digest_prefix": "old123",
            },
        )
        # Manually backdate the old row via a direct SQL update so it
        # falls outside the TTL window.
        from core.persistence import get_connection

        old_ts = (datetime.now(timezone.utc) - timedelta(hours=200)).isoformat()
        with get_connection() as conn:
            conn.execute(
                "UPDATE decision_ledger SET created_at = ? "
                "WHERE action_id = ?",
                (old_ts, "act-old"),
            )
        decision_ledger.append(
            tenant,
            {
                "action_id": "act-fresh1",
                "specialist": "Kian",
                "decision": "reject",
                "reason_code": "DUPLICATE",
                "digest_prefix": "frsh1",
            },
        )
        decision_ledger.append(
            tenant,
            {
                "action_id": "act-fresh2",
                "specialist": "Bita",
                "decision": "approve",
                "digest_prefix": "frsh2",
            },
        )
        # TTL=168h default → only the two fresh rows should return.
        rows = decision_ledger.recent(tenant)
        action_ids = [r["action_id"] for r in rows]
        self.assertNotIn("act-old", action_ids)
        self.assertIn("act-fresh1", action_ids)
        self.assertIn("act-fresh2", action_ids)
        # Cap n=1 → only one row.
        rows_capped = decision_ledger.recent(tenant, n=1)
        self.assertEqual(len(rows_capped), 1)
        # Newest last → the capped row is the newest fresh row.
        self.assertEqual(rows_capped[-1]["action_id"], "act-fresh2")

    # ------------------------------------------------------------------ #
    # 2) neighbor recent empty
    # ------------------------------------------------------------------ #
    def test_neighbor_recent_empty(self) -> None:
        """A neighbor tenant sees [] from recent()."""
        tenant_a = "t212-neighbor-a"
        tenant_b = "t212-neighbor-b"
        decision_ledger.append(
            tenant_a,
            {
                "action_id": "act-a1",
                "specialist": "Alina",
                "decision": "approve",
            },
        )
        rows_b = decision_ledger.recent(tenant_b)
        self.assertEqual(rows_b, [])
        rows_a = decision_ledger.recent(tenant_a)
        self.assertEqual(len(rows_a), 1)

    # ------------------------------------------------------------------ #
    # 3) propose includes hint after approve
    # ------------------------------------------------------------------ #
    def test_propose_includes_hint_after_approve(self) -> None:
        """After an approve the next propose response has a non-empty hint."""
        tenant = "t212-hint-approve"
        _seed_profile(tenant)
        app = create_app()
        client = TestClient(app)
        # First propose → no prior decisions → empty hint.
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("last_decisions_hint", body)
        self.assertEqual(body["last_decisions_hint"], "")
        proposals = body.get("proposals", [])
        self.assertGreater(len(proposals), 0)
        action_id = proposals[0]["action_id"]
        digest = proposals[0].get("payload_sha256", "")
        self.assertTrue(digest)
        # Approve one action.
        resp2 = client.post(
            f"/api/v1/twin/actions/{action_id}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": digest,
            },
        )
        self.assertEqual(resp2.status_code, 200)
        # Second propose → hint should be non-empty.
        resp3 = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp3.status_code, 200)
        body3 = resp3.json()
        self.assertIn("last_decisions_hint", body3)
        self.assertTrue(body3["last_decisions_hint"])

    # ------------------------------------------------------------------ #
    # 4) forget clears hint on next propose
    # ------------------------------------------------------------------ #
    def test_forget_clears_hint_on_next_propose(self) -> None:
        """After Forget the next propose response has an empty hint."""
        tenant = "t212-forget-hint"
        _seed_profile(tenant)
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json().get("proposals", [])
        self.assertGreater(len(proposals), 0)
        action_id = proposals[0]["action_id"]
        digest = proposals[0].get("payload_sha256", "")
        self.assertTrue(digest)
        client.post(
            f"/api/v1/twin/actions/{action_id}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": digest,
            },
        )
        # Forget the ledger.
        decision_ledger.forget(tenant)
        # Next propose → empty hint.
        resp2 = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.json()
        self.assertIn("last_decisions_hint", body2)
        self.assertEqual(body2["last_decisions_hint"], "")

    # ------------------------------------------------------------------ #
    # 5) no auto-execute from hint
    # ------------------------------------------------------------------ #
    def test_no_auto_execute_from_hint(self) -> None:
        """A hint on the propose card does not cause execution."""
        tenant = "t212-no-autoexec"
        _seed_profile(tenant)
        app = create_app()
        client = TestClient(app)
        # Propose + approve one action so the ledger has a row.
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp.status_code, 200)
        proposals = resp.json().get("proposals", [])
        self.assertGreater(len(proposals), 0)
        action_id = proposals[0]["action_id"]
        digest = proposals[0].get("payload_sha256", "")
        self.assertTrue(digest)
        client.post(
            f"/api/v1/twin/actions/{action_id}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": digest,
            },
        )
        # Second propose — the new proposals should all be "proposed",
        # not "executed", even though the hint cites a prior approve.
        resp2 = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "review tasks", "training": False},
        )
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.json()
        self.assertTrue(body2.get("last_decisions_hint", ""))
        for prop in body2.get("proposals", []):
            self.assertEqual(prop["status"], "proposed")

    # ------------------------------------------------------------------ #
    # 6) README mentions TTL or next propose
    # ------------------------------------------------------------------ #
    def test_readme_mentions_ttl_or_next_propose(self) -> None:
        """README mentions TTL or next propose."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertTrue(
            "ttl" in text or "next propose" in text,
            "README does not mention TTL or next propose",
        )

    # ------------------------------------------------------------------ #
    # 7) README does not claim two week
    # ------------------------------------------------------------------ #
    def test_readme_does_not_claim_two_week(self) -> None:
        """README has no two-week or two week."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn("two-week", text)
        self.assertNotIn("two week", text)

    # ------------------------------------------------------------------ #
    # 8) README does not claim multi-month twin
    # ------------------------------------------------------------------ #
    def test_readme_does_not_claim_multi_month_twin(self) -> None:
        """README has no multi-month twin."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn("multi-month twin", text)
        self.assertNotIn("multimonth twin", text)

    # ------------------------------------------------------------------ #
    # 9) STATUS has T212 line
    # ------------------------------------------------------------------ #
    def test_status_has_t212_line(self) -> None:
        """STATUS.md contains T212."""
        text = _STATUS.read_text(encoding="utf-8")
        self.assertIn("T212", text)

    # ------------------------------------------------------------------ #
    # 10) core/ has no Stripe token
    # ------------------------------------------------------------------ #
    def test_core_tree_has_no_stripe_token(self) -> None:
        """No live Stripe secret token in core/."""
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
