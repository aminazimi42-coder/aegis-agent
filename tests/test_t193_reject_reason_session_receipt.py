"""T193 — Last reject reason on next propose and local session receipt.

Covers:

* ``test_next_propose_includes_last_reject_reason`` — after a reject with a
  T117 enum, the next propose response includes ``last_reject_reason``.
* ``test_no_prior_reject_omits_or_empty_reason`` — when the tenant has never
  rejected, ``last_reject_reason`` is omitted.
* ``test_reason_is_t117_enum_only`` — the returned reason is one of the T117
  enum labels, not a free-text string.
* ``test_html_shows_last_reject_line_when_present`` — the operator HTML
  contains a ``last-reject-label`` span and the ``Last reject:`` prefix.
* ``test_session_receipt_written_after_propose`` — a receipt JSON is written
  under ``<AEGIS_DATA_DIR>/receipts/`` after a propose.
* ``test_session_receipt_written_after_approve`` — a receipt is written after
  an approve.
* ``test_session_receipt_written_after_reject`` — a receipt is written after
  a reject.
* ``test_receipt_stays_inside_data_dir`` — the receipt path is inside the
  configured ``AEGIS_DATA_DIR``.
* ``test_receipt_has_no_stripe_and_no_cloud_url`` — the receipt JSON has no
  Stripe fields and no cloud URL.
* ``test_readme_author_untouched`` — the README Author paragraph is present
  and unchanged.
* ``test_readme_does_not_contain_notarized`` — the word *notarized* does not
  appear in the README.

No uvicorn.  ``tmp_path`` only.  No ``xfail``.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from core.twin_actions import (
    REJECT_REASON_ENUM,
    _action_digest,
    _load_action,
    insert_specialist_proposal,
    propose_actions,
    reject,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT193(unittest.TestCase):
    """T193 — last reject reason on next propose and local session receipt."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t193_")
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

    # ------------------------------------------------------------------ #
    # 1) Next propose includes last reject reason
    # ------------------------------------------------------------------ #

    def test_next_propose_includes_last_reject_reason(self) -> None:
        """After a reject with a T117 enum, the next propose includes it."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t193_reject_reason"
        self._full_interview(tenant)
        # Propose and reject one action.
        actions = propose_actions(tenant)
        action_id = actions[0]["action_id"]
        reject(action_id, tenant_id=tenant, reason_enum="POLICY_VIOLATION")

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "new task"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("last_reject_reason", body)
        self.assertTrue(body["last_reject_reason"])

    # ------------------------------------------------------------------ #
    # 2) No prior reject omits or empty reason
    # ------------------------------------------------------------------ #

    def test_no_prior_reject_omits_or_empty_reason(self) -> None:
        """When the tenant has never rejected, last_reject_reason is omitted."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t193_no_reject"
        self._full_interview(tenant)

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "fresh task"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn("last_reject_reason", body)

    # ------------------------------------------------------------------ #
    # 3) Reason is T117 enum only
    # ------------------------------------------------------------------ #

    def test_reason_is_t117_enum_only(self) -> None:
        """The last_reject_reason is one of the T117 enum labels."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t193_enum_only"
        self._full_interview(tenant)
        actions = propose_actions(tenant)
        action_id = actions[0]["action_id"]
        reject(action_id, tenant_id=tenant, reason_enum="DUPLICATE")

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "enum check"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("last_reject_reason", body)
        reason = body["last_reject_reason"]
        self.assertIn(reason, REJECT_REASON_ENUM)

    # ------------------------------------------------------------------ #
    # 4) HTML shows last reject line when present
    # ------------------------------------------------------------------ #

    def test_html_shows_last_reject_line_when_present(self) -> None:
        """The operator HTML contains the last-reject-label span."""
        html = Path("app.html").read_text("utf-8")
        self.assertIn("last-reject-label", html)
        self.assertIn("Last reject:", html)
        # Desktop bundle matches repo.
        desk = Path(
            "desktop/macos/Aegis.app/Contents/Resources/app.html"
        ).read_text("utf-8")
        self.assertEqual(html, desk)

    # ------------------------------------------------------------------ #
    # 5) Session receipt written after propose
    # ------------------------------------------------------------------ #

    def test_session_receipt_written_after_propose(self) -> None:
        """A receipt JSON is written under AEGIS_DATA_DIR/receipts/ after propose."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t193_receipt_propose"
        self._full_interview(tenant)

        client = TestClient(create_app())
        resp = client.post(
            "/api/v1/twin/propose",
            json={"tenant_id": tenant, "text": "receipt test"},
        )
        self.assertEqual(resp.status_code, 200)

        receipts_dir = Path(self._tmp) / "receipts"
        self.assertTrue(receipts_dir.is_dir())
        files = list(receipts_dir.glob("session_*.json"))
        self.assertGreater(len(files), 0)
        data = json.loads(files[0].read_text("utf-8"))
        self.assertEqual(data["tenant_id"], tenant)
        self.assertEqual(data["last_event"], "propose")

    # ------------------------------------------------------------------ #
    # 6) Session receipt written after approve
    # ------------------------------------------------------------------ #

    def test_session_receipt_written_after_approve(self) -> None:
        """A receipt JSON is written after an approve."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t193_receipt_approve"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "T193 approve receipt", {"body": "approve test"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        digest = _action_digest(action)

        app = create_app()
        client = TestClient(app)
        resp = client.post(
            f"/api/v1/twin/actions/{action_id}/approve",
            json={
                "tenant_id": tenant,
                "actor_id": "operator",
                "expected_payload_sha256": digest,
            },
        )
        self.assertEqual(resp.status_code, 200)

        receipts_dir = Path(self._tmp) / "receipts"
        files = list(receipts_dir.glob("session_*.json"))
        self.assertGreater(len(files), 0)
        # Find the approve receipt.
        found = False
        for f in files:
            data = json.loads(f.read_text("utf-8"))
            if data.get("last_event") == "approve":
                self.assertEqual(data["tenant_id"], tenant)
                self.assertEqual(data.get("last_action_id"), action_id)
                found = True
                break
        self.assertTrue(found, "no approve receipt found")

    # ------------------------------------------------------------------ #
    # 7) Session receipt written after reject
    # ------------------------------------------------------------------ #

    def test_session_receipt_written_after_reject(self) -> None:
        """A receipt JSON is written after a reject."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        tenant = "t193_receipt_reject"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "T193 reject receipt", {"body": "reject test"}
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
                "reason_enum": "WRONG_TIMING",
            },
        )
        self.assertEqual(resp.status_code, 200)

        receipts_dir = Path(self._tmp) / "receipts"
        files = list(receipts_dir.glob("session_*.json"))
        self.assertGreater(len(files), 0)
        found = False
        for f in files:
            data = json.loads(f.read_text("utf-8"))
            if data.get("last_event") == "reject":
                self.assertEqual(data["tenant_id"], tenant)
                self.assertEqual(data.get("last_reject_reason"), "WRONG_TIMING")
                found = True
                break
        self.assertTrue(found, "no reject receipt found")

    # ------------------------------------------------------------------ #
    # 8) Receipt stays inside data dir
    # ------------------------------------------------------------------ #

    def test_receipt_stays_inside_data_dir(self) -> None:
        """The receipt path is inside AEGIS_DATA_DIR."""
        from core.session_receipt import write_session_receipt

        path = write_session_receipt(
            "t193_cage",
            session_id="t193_cage_sid",
            last_event="propose",
        )
        root = Path(self._tmp).resolve()
        self.assertTrue(
            path.resolve().is_relative_to(root),
            f"receipt {path} is outside {root}",
        )

    # ------------------------------------------------------------------ #
    # 9) Receipt has no Stripe and no cloud URL
    # ------------------------------------------------------------------ #

    def test_receipt_has_no_stripe_and_no_cloud_url(self) -> None:
        """The receipt JSON has no payment fields and no cloud URL."""
        from core.session_receipt import write_session_receipt

        path = write_session_receipt(
            "t193_no_pay",
            session_id="t193_no_pay_sid",
            last_event="propose",
        )
        text = path.read_text("utf-8")
        lower = text.lower()
        self.assertNotIn("stripe", lower)
        self.assertNotIn("card", lower)
        self.assertNotIn("https://", lower)
        self.assertNotIn("http://", lower)
        # Verify required keys are present.
        data = json.loads(text)
        for key in (
            "tenant_id",
            "session_id",
            "last_event",
            "last_action_id",
            "last_reject_reason",
            "updated_at",
            "engine",
        ):
            self.assertIn(key, data)

    # ------------------------------------------------------------------ #
    # 10) README author untouched
    # ------------------------------------------------------------------ #

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and unchanged."""
        text = Path("README.md").read_text("utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 11) README does not contain notarized
    # ------------------------------------------------------------------ #

    def test_readme_does_not_contain_notarized(self) -> None:
        """The word *notarized* does not appear in the README."""
        text = Path("README.md").read_text("utf-8")
        lower = text.lower()
        self.assertNotIn("nota" + "rized", lower)


if __name__ == "__main__":
    unittest.main()
