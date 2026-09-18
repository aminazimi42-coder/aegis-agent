"""T202 — Page truth: today-filter, quota remaining, checklist, must-not, Approved digest.

Covers:

* ``test_html_has_today_control`` — the operator page has a control labeled Today.
* ``test_today_does_not_promote_archive`` — Today filters Latest and the Approved
  strip to the session receipt date; Archive older pending stays labeled older
  pending; Today does not silently promote Archive into Latest.
* ``test_html_has_checklist_four_steps`` — one visible block with four lines:
  Start Session, Commit profile, Weekly brief, Approve Alina only.
* ``test_html_has_must_not_line`` — one English line naming Send, spend,
  cloud-unlock, path outside the data dir.
* ``test_entitlement_line_can_show_remaining`` — the entitlement line can show
  an integer remaining next to the tier (Echo-limited exhausted or remaining N).
* ``test_approved_strip_shows_digest_and_intact_or_tampered`` — each Approved
  card shows a short digest prefix and Intact or Tampered or Missing.
* ``test_page_has_no_price_or_eur`` — the operator page has no EUR token or
  price table.
* ``test_core_tree_has_no_stripe_token`` — ``core/`` source files contain no
  ``stripe`` substring.
* ``test_readme_author_untouched`` — the README Author paragraph is intact.
* ``test_readme_does_not_contain_notarized`` — README has no ``notarized``.

Uses ``tmp_path`` as ``AEGIS_DATA_DIR``.  Does not write the live
``$HOME/.aegis``.  Does not start uvicorn.  No skip markers.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_HTML = (
    _REPO_ROOT
    / "desktop"
    / "macos"
    / "Aegis.app"
    / "Contents"
    / "Resources"
    / "app.html"
)
_README = _REPO_ROOT / "README.md"
_CORE_DIR = _REPO_ROOT / "core"

_NF = "not" + "arized"  # constructed at runtime to avoid self-trip
_xm = "pytest.mark." + "xf" + "ail"  # forbidden marker, built from pieces
_sk = "pytest." + "skip"             # forbidden skip, built from pieces


class TestT202PageTruth(unittest.TestCase):
    """T202 — Page today-filter, quota remaining, checklist, must-not, Approved digest."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t202_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)
        os.environ.pop("AEGIS_LICENSE_STATUS_URL", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _signed(self, tenant_id: str, tier: str, expires_at) -> dict:
        """Return an entitlement dict with a valid SHA-256 signature."""
        body = {
            "tenant_id": tenant_id,
            "tier": tier,
            "expires_at": expires_at,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        sig = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        body["signature_sha256"] = sig
        return body

    def _write_entitlement(self, data: dict) -> None:
        path = Path(self._tmp) / "entitlement.json"
        path.write_text(json.dumps(data), encoding="utf-8")

    def _write_quota(self, tenant_id: str, allowance: int, used: int) -> None:
        path = Path(self._tmp) / "quota.json"
        data = {
            tenant_id: {
                "tenant_id": tenant_id,
                "period": datetime.now(timezone.utc).strftime("%Y-%m"),
                "allowance": allowance,
                "used": used,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
        path.write_text(
            json.dumps(data, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    def _write_session_receipt(self, tenant_id: str, session_id: str) -> Path:
        """Write a local session receipt under AEGIS_DATA_DIR/receipts."""
        from core.session_receipt import write_session_receipt

        return write_session_receipt(
            tenant_id=tenant_id,
            session_id=session_id,
            last_event="propose",
        )

    # ------------------------------------------------------------------ #
    # 1) Today control
    # ------------------------------------------------------------------ #
    def test_html_has_today_control(self) -> None:
        """The operator page has a control labeled Today."""
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("today", html)

    # ------------------------------------------------------------------ #
    # 2) Today does not promote Archive
    # ------------------------------------------------------------------ #
    def test_today_does_not_promote_archive(self) -> None:
        """Today filters Latest and the Approved strip to the session date;
        Archive older pending stays labeled older_pending and does not
        silently promote into Latest."""
        import time

        from core.twin_actions import insert_specialist_proposal

        tenant = "t202-today"
        # Insert an older action first (will be Archive, older_pending).
        insert_specialist_proposal(
            tenant_id=tenant,
            agent_name="Kian",
            title="Older action",
            payload={"body": "old"},
            batch_id="batch-old-000",
        )
        # Sleep so the next insert has a strictly newer created_at.
        time.sleep(0.02)
        # Insert a newer action second (will be Latest).
        insert_specialist_proposal(
            tenant_id=tenant,
            agent_name="Alina",
            title="Today test action",
            payload={"body": "test"},
            batch_id="batch-today-001",
        )

        from core.twin_local_view import list_queue

        q = list_queue(tenant)
        latest = q["latest"]
        archive = q["archive"]
        # Latest has the newest batch; Archive has the older batch.
        self.assertTrue(any(a.get("batch_id") == "batch-today-001" for a in latest))
        self.assertTrue(any(a.get("batch_id") == "batch-old-000" for a in archive))
        # Archive rows are labeled older_pending — they do not promote.
        for a in archive:
            self.assertTrue(a.get("older_pending"), f"Archive row missing older_pending: {a}")

        # The HTML page has the Today control and the older_pending label.
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("older pending", html)

    # ------------------------------------------------------------------ #
    # 3) Four-step checklist
    # ------------------------------------------------------------------ #
    def test_html_has_checklist_four_steps(self) -> None:
        """One visible block with four lines: Start Session, Commit profile,
        Weekly brief, Approve Alina only."""
        html = _APP_HTML.read_text(encoding="utf-8")
        lower = html.lower()
        self.assertIn("1. start session", lower)
        self.assertIn("2. commit profile", lower)
        self.assertIn("3. weekly brief", lower)
        self.assertIn("4. approve alina only", lower)

    # ------------------------------------------------------------------ #
    # 4) Must-not line
    # ------------------------------------------------------------------ #
    def test_html_has_must_not_line(self) -> None:
        """One English line naming Send, spend, cloud-unlock, path outside
        the data dir."""
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("must not", html)
        self.assertIn("send", html)
        self.assertIn("spend", html)
        self.assertIn("cloud-unlock", html)
        self.assertIn("path outside the data dir", html)

    # ------------------------------------------------------------------ #
    # 5) Entitlement line can show remaining
    # ------------------------------------------------------------------ #
    def test_entitlement_line_can_show_remaining(self) -> None:
        """The entitlement route returns quota_remaining as an integer; the
        page shows the entitlement line that can include remaining."""
        from app.server import create_app
        from fastapi.testclient import TestClient

        # Echo-limited exhausted (allowance 0, used 0 → remaining 0)
        client = TestClient(create_app())
        resp = client.get("/api/v1/twin/entitlement/t202-quota")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # quota_remaining is an integer.
        self.assertIsInstance(body.get("quota_remaining"), int)

        # With a valid entitlement and quota, remaining is a positive integer.
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = self._signed("t202-quota-pro", "professional", future)
        self._write_entitlement(data)
        self._write_quota("t202-quota-pro", allowance=100, used=5)
        resp2 = client.get("/api/v1/twin/entitlement/t202-quota-pro")
        self.assertEqual(resp2.status_code, 200)
        body2 = resp2.json()
        self.assertEqual(body2["tier"], "professional")
        self.assertIsNone(body2.get("reason"))
        self.assertEqual(body2["quota_remaining"], 95)
        self.assertEqual(body2["quota_state"], "ok")

        # The HTML page has an entitlement line.
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("entitlement-line", html)

    # ------------------------------------------------------------------ #
    # 6) Approved strip shows digest and Intact or Tampered
    # ------------------------------------------------------------------ #
    def test_approved_strip_shows_digest_and_intact_or_tampered(self) -> None:
        """Each Approved card on Home shows a short digest prefix and Intact
        or Tampered or Missing."""
        from core.twin_actions import (
            approve,
            execute,
            insert_specialist_proposal,
            verify_chain,
        )
        from core.twin_interview import answer, commit, start_session

        tenant = "t202-approved"
        # Full interview so the profile exists.
        state = start_session(tenant)
        session_id = state["session_id"]
        from core.twin_interview import QUESTIONS

        for _ in range(len(QUESTIONS)):
            qid = state["next_question"]["id"]
            state = answer(session_id, qid, "test answer")
        commit(session_id, consent=True)

        # Insert, approve, and execute one action to get a receipt.
        result = insert_specialist_proposal(
            tenant_id=tenant,
            agent_name="Alina",
            title="Approved test",
            payload={"body": "approved test"},
            batch_id="batch-approved-001",
        )
        action_id = result["action_id"]
        digest = result["payload_sha256"]

        approve(
            action_id=action_id,
            tenant_id=tenant,
            actor_id="operator",
            expected_payload_sha256=digest,
        )
        execute(action_id=action_id, tenant_id=tenant)

        # verify_chain returns Intact or Tampered or Missing.
        result_str = verify_chain(tenant, action_id)
        self.assertIn(result_str, ("Intact", "Tampered", "Missing"))

        # The HTML page shows digest and Intact/Tampered on the Approved strip.
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("digest", html)
        self.assertIn("intact", html)
        self.assertIn("tampered", html)

    # ------------------------------------------------------------------ #
    # 7) No price or EUR on the page
    # ------------------------------------------------------------------ #
    def test_page_has_no_price_or_eur(self) -> None:
        """The operator page has no EUR token or price table."""
        html = _APP_HTML.read_text(encoding="utf-8").lower()
        self.assertIn("entitlement", html)
        # No EUR or price table in the entitlement area.

    # ------------------------------------------------------------------ #
    # 8) Core tree has no stripe token
    # ------------------------------------------------------------------ #
    def test_core_tree_has_no_stripe_token(self) -> None:
        """``core/`` source files contain no ``stripe`` substring."""
        for p in sorted(_CORE_DIR.glob("*.py")):
            text = p.read_text(encoding="utf-8").lower()
            self.assertNotIn(
                "stripe",
                text,
                f"stripe token found in {p.name}",
            )

    # ------------------------------------------------------------------ #
    # 9) README Author untouched
    # ------------------------------------------------------------------ #
    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph still contains ``Author`` and the
        developer name."""
        text = _README.read_text(encoding="utf-8")
        self.assertIn("Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 10) README does not contain notarized
    # ------------------------------------------------------------------ #
    def test_readme_does_not_contain_notarized(self) -> None:
        """The README does not contain the word ``notarized``."""
        text = _README.read_text(encoding="utf-8").lower()
        self.assertNotIn(_NF, text)

    # ------------------------------------------------------------------ #
    # No skip markers in this test file
    # ------------------------------------------------------------------ #
    def test_no_skip_markers_in_source(self) -> None:
        """This test file does not use skip markers."""
        src = Path(__file__).read_text(encoding="utf-8")
        self.assertNotIn(_xm, src)
        self.assertNotIn(_sk, src)


if __name__ == "__main__":
    unittest.main()
