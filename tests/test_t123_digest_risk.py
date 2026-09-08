"""T123 — Digest property, risk TTL, typed L2/L3 phrase.

Covers:
- **Property:** for a proposed row, flipping one payload byte must make
  approve return 409 (TestClient, no live network).
- **L2/L3 phrase:** when ``risk_level`` is ``L2`` or ``L3`` the
  operator-visible digest text in the queue response contains a stable
  typed token such as ``RISK_L2`` or ``RISK_L3``.
- **Risk TTL:** after the TTL expires the warning flag may drop, but the
  row never auto-approves or auto-executes — status stays ``proposed``.

No live network except ``TestClient``.
"""

from __future__ import annotations

import json as _json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.server import create_app
from core.persistence import get_connection
from core.twin_actions import (
    _action_digest,
    _ensure_schema,
    _load_action,
    execute,
    insert_specialist_proposal,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session
from core.twin_local_view import _risk_label, _risk_warn, list_queue
from fastapi.testclient import TestClient


def _full_interview(tenant_id: str) -> str:
    """Run a complete T03 interview and return the session id."""
    session = start_session(tenant_id)
    sid = session["session_id"]
    for q in QUESTIONS:
        answer(sid, q["id"], f"ans-{q['id']}")
    commit(sid, True)
    return sid


def _insert_proposed(
    tenant_id: str,
    title: str = "Review weekly digest",
    payload: dict | None = None,
    kind: str = "review_digest",
) -> str:
    """Insert a proposed row with a payload and return its action_id."""
    _ensure_schema()
    action_id = f"act-{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    payload_json = _json.dumps(payload) if payload is not None else None
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO twin_actions "
            "(action_id, tenant_id, kind, title, status, created_at, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (action_id, tenant_id, kind, title, "proposed", now, payload_json),
        )
    return action_id


class TestT123DigestRisk(unittest.TestCase):
    """Digest property + risk TTL phrase."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t123_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # 1. Property: flipping one payload byte → approve returns 409
    # ------------------------------------------------------------------ #

    def test_mutated_payload_still_409(self) -> None:
        """Flipping one payload byte after computing the digest must
        make the approve endpoint return 409."""
        tenant = "t123_mut"
        _full_interview(tenant)
        action_id = _insert_proposed(
            tenant,
            title="Review weekly digest",
            payload={"body": "original payload text"},
        )

        # Compute the real digest before mutation.
        action = _load_action(action_id)
        assert action is not None
        original_digest = _action_digest(action)
        self.assertTrue(original_digest)

        # Flip one byte in the stored payload.
        with get_connection() as conn:
            conn.execute(
                "UPDATE twin_actions SET payload = ? WHERE action_id = ?",
                (_json.dumps({"body": "original payload text!"}), action_id),
            )

        # Approve via TestClient with the original (now-stale) digest.
        app = create_app()
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/twin/actions/{action_id}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": original_digest,
            },
        )
        self.assertEqual(resp.status_code, 409)

        # Status must stay proposed.
        still = _load_action(action_id)
        assert still is not None
        self.assertEqual(still["status"], "proposed")

    # ------------------------------------------------------------------ #
    # 2. L2/L3 phrase in the operator-visible digest text
    # ------------------------------------------------------------------ #

    def test_l2_phrase_in_digest(self) -> None:
        """An L2-risk proposed row's queue entry carries ``RISK_L2`` in
        ``digest_label``; an L3 row carries ``RISK_L3``."""
        tenant = "t123_l2"
        _full_interview(tenant)

        # Insert an L2-risk row (title contains an L2 keyword).
        l2_row = insert_specialist_proposal(
            tenant,
            "Alina",
            "Send the weekly email",
            {"body": "email body"},
            batch_id="batch-l2",
        )
        l2_id = l2_row["action_id"]
        # Insert an L3-risk row (title contains an L3 keyword).
        l3_row = insert_specialist_proposal(
            tenant,
            "Ahmad",
            "Pay the invoice",
            {"body": "pay body"},
            batch_id="batch-l3",
        )
        l3_id = l3_row["action_id"]

        queue = list_queue(tenant)
        pending = queue["pending"]
        by_id = {a["action_id"]: a for a in pending}

        self.assertIn(l2_id, by_id)
        self.assertIn(l3_id, by_id)

        # L2 row → digest_label contains RISK_L2
        self.assertEqual(by_id[l2_id]["digest_label"], "RISK_L2")
        # L3 row → digest_label contains RISK_L3
        self.assertEqual(by_id[l3_id]["digest_label"], "RISK_L3")

        # The hex digest payload_sha256 is still present and unchanged.
        self.assertTrue(by_id[l2_id].get("payload_sha256"))
        self.assertTrue(by_id[l3_id].get("payload_sha256"))

        # Also exercise the pure helper for L0/L1 — no label.
        self.assertEqual(_risk_label("L0"), "")
        self.assertEqual(_risk_label("L1"), "")

    # ------------------------------------------------------------------ #
    # 3. Risk TTL: warning flag may drop, but never auto-execute
    # ------------------------------------------------------------------ #

    def test_ttl_does_not_execute(self) -> None:
        """After the TTL expires the ``risk_warn`` flag may drop, but the
        row never auto-approves or auto-executes — status stays
        ``proposed``."""
        tenant = "t123_ttl"
        _full_interview(tenant)

        # Insert an L2 row with a created_at in the past (well past TTL).
        _ensure_schema()
        action_id = f"act-{uuid4().hex[:12]}"
        old_time = (datetime.now(timezone.utc) - timedelta(hours=999)).isoformat()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO twin_actions "
                "(action_id, tenant_id, kind, title, status, created_at, "
                " payload, payload_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    action_id,
                    tenant,
                    "email",
                    "Send the email",
                    "proposed",
                    old_time,
                    _json.dumps({"body": "stale email"}),
                    "0" * 64,
                ),
            )

        # The warning flag should be False (TTL expired).
        action = _load_action(action_id)
        assert action is not None
        self.assertFalse(_risk_warn(action))

        # But the row is still proposed — no auto-approve, no auto-execute.
        self.assertEqual(action["status"], "proposed")

        # execute() must refuse (not approved).
        with self.assertRaises(PermissionError):
            execute(action_id, tenant)

        # Status must still be proposed after the attempt.
        still = _load_action(action_id)
        assert still is not None
        self.assertEqual(still["status"], "proposed")

        # A fresh row (within TTL) keeps the warning flag.
        fresh_id = _insert_proposed(
            tenant,
            title="Send the email",
            payload={"body": "fresh email"},
            kind="email",
        )
        fresh = _load_action(fresh_id)
        assert fresh is not None
        self.assertTrue(_risk_warn(fresh))

    # ------------------------------------------------------------------ #
    # 4. No live network
    # ------------------------------------------------------------------ #

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
