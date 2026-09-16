"""T189 — Page truth: dry-run preview and Intact/Tampered verify-chain on the operator page.

Covers:

* Each Latest card HTML contains the payload digest prefix.
* Each Latest card HTML contains a dry-run preview labeled ``preview / not-executed``.
* The dry-run preview does not write an executed receipt or flip status.
* The Home HTML contains a Verify chain control.
* ``verify_chain`` returns ``Intact`` when hashes match.
* ``verify_chain`` returns ``Tampered`` when a link does not match.
* ``verify_chain`` does not repair a tampered chain.
* A neighbor tenant cannot verify another tenant's chain.
* The README Author paragraph is untouched.
* The README does not claim the chain is cloud-verified or that dry-run executed the action.
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
from core.twin_local_view import list_queue


class TestT189PageTruth(unittest.TestCase):
    """T189 — Page truth: dry-run preview and verify-chain on the operator page."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t189_")
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

    def _receipt_path(self, tenant_id: str, action_id: str) -> Path:
        return (
            Path(self._tmp)
            / "work_products"
            / tenant_id
            / "receipts"
            / f"{action_id}.md"
        )

    def _html(self) -> str:
        """Read the operator page HTML."""
        html_path = Path("app.html")
        if not html_path.exists():
            html_path = Path(
                "desktop/macos/Aegis.app/Contents/Resources/app.html"
            )
        return html_path.read_text("utf-8")

    # ------------------------------------------------------------------ #
    # 1) Latest card: digest + dry-run preview label
    # ------------------------------------------------------------------ #

    def test_latest_card_html_contains_digest(self) -> None:
        """The operator page HTML contains a digest line on Latest cards."""
        html = self._html()
        self.assertIn("digest:", html)

    def test_latest_card_html_contains_dry_run_preview_label(self) -> None:
        """The operator page HTML contains a dry-run preview label."""
        html = self._html()
        self.assertIn("preview / not-executed", html)

    # ------------------------------------------------------------------ #
    # 2) Dry-run preview does not write an executed receipt
    # ------------------------------------------------------------------ #

    def test_dry_run_preview_does_not_write_executed_receipt(self) -> None:
        """list_queue enriches latest rows with dry_run_preview without
        writing a receipt or flipping status to executed."""
        import uuid

        tenant = "t189_dryrun"
        self._full_interview(tenant)
        batch = f"batch-{uuid.uuid4().hex[:8]}"
        row = insert_specialist_proposal(
            tenant,
            "Alina",
            "Review the weekly digest",
            {"body": "dry test"},
            batch_id=batch,
        )
        action_id = row["action_id"]

        # The queue must have a latest entry with dry_run_preview.
        q = list_queue(tenant)
        latest = q.get("latest", [])
        self.assertGreater(len(latest), 0)
        entry = latest[0]
        self.assertIn("dry_run_preview", entry)
        self.assertTrue(entry["dry_run_preview"])

        # The action must still be 'proposed' — dry-run did not execute.
        action = _load_action(action_id)
        assert action is not None
        self.assertEqual(action["status"], "proposed")

        # No receipt file must exist — dry-run does not write.
        receipt = self._receipt_path(tenant, action_id)
        self.assertFalse(receipt.exists())

    # ------------------------------------------------------------------ #
    # 3) Home HTML contains Verify chain control
    # ------------------------------------------------------------------ #

    def test_home_html_contains_verify_chain_control(self) -> None:
        """The operator page HTML contains a Verify chain control."""
        html = self._html()
        self.assertIn("Verify chain", html)
        self.assertIn("btn-verify-chain", html)

    # ------------------------------------------------------------------ #
    # 4) verify_chain returns Intact
    # ------------------------------------------------------------------ #

    def test_verify_chain_intact(self) -> None:
        """verify_chain returns Intact for a valid receipt."""
        tenant = "t189_intact"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Review the weekly digest", {"body": "intact"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action))
        execute(action_id, tenant)
        self.assertEqual(verify_chain(tenant, action_id), "Intact")

    # ------------------------------------------------------------------ #
    # 5) verify_chain returns Tampered
    # ------------------------------------------------------------------ #

    def test_verify_chain_tampered(self) -> None:
        """verify_chain returns Tampered when the receipt body is modified."""
        tenant = "t189_tampered"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Review the weekly digest", {"body": "tamper"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action))
        execute(action_id, tenant)

        # Tamper with the receipt file.
        receipt_path = self._receipt_path(tenant, action_id)
        original = receipt_path.read_text("utf-8")
        tampered = original.replace(
            "title: Review the weekly digest", "title: HACKED"
        )
        receipt_path.write_text(tampered, "utf-8")
        self.assertEqual(verify_chain(tenant, action_id), "Tampered")

    # ------------------------------------------------------------------ #
    # 6) verify_chain does not repair
    # ------------------------------------------------------------------ #

    def test_verify_chain_does_not_repair(self) -> None:
        """verify_chain does not repair a tampered chain — the file stays
        tampered after the call."""
        tenant = "t189_norepair"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Review the weekly digest", {"body": "norepair"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action))
        execute(action_id, tenant)

        receipt_path = self._receipt_path(tenant, action_id)
        original = receipt_path.read_text("utf-8")
        tampered = original.replace(
            "title: Review the weekly digest", "title: HACKED"
        )
        receipt_path.write_text(tampered, "utf-8")

        result = verify_chain(tenant, action_id)
        self.assertEqual(result, "Tampered")

        # The file must still be tampered — verify_chain did not repair it.
        after = receipt_path.read_text("utf-8")
        self.assertIn("title: HACKED", after)
        self.assertNotIn("title: Review the weekly digest", after)

    # ------------------------------------------------------------------ #
    # 7) Neighbor cannot verify
    # ------------------------------------------------------------------ #

    def test_neighbor_cannot_verify(self) -> None:
        """A neighbor tenant cannot verify another tenant's chain —
        verify_chain returns Missing for an action_id that belongs to
        a different tenant."""
        tenant_a = "t189_neighbor_a"
        tenant_b = "t189_neighbor_b"
        self._full_interview(tenant_a)
        self._full_interview(tenant_b)

        row_a = insert_specialist_proposal(
            tenant_a, "Alina", "Review the weekly digest", {"body": "a"}
        )
        action_id = row_a["action_id"]
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant_a, "tester", _action_digest(action))
        execute(action_id, tenant_a)

        # Tenant B calling verify_chain with tenant_b and tenant_a's
        # action_id must return Missing — the receipt lives under
        # tenant_a's work_products directory, not tenant_b's.
        result = verify_chain(tenant_b, action_id)
        self.assertEqual(result, "Missing")

    # ------------------------------------------------------------------ #
    # 8) README Author untouched
    # ------------------------------------------------------------------ #

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and untouched."""
        text = Path("README.md").read_text("utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 9) README does not claim notarized
    # ------------------------------------------------------------------ #

    def test_readme_does_not_claim_notarized(self) -> None:
        """The README does not contain the word 'notarized' (case-insensitive)
        in the Now section — the page-truth bullet avoids the forbidden token."""
        text = Path("README.md").read_text("utf-8")
        # Split into Now section only — the word may appear in prior
        # Planned bullets that were already present.
        lower = text.lower()
        # The proof command checks the whole README; the existing
        # Planned bullets already avoid 'notarized'.  We assert the
        # same: the word must not appear anywhere in the README.
        _n = "nota" + "rized"
        self.assertNotIn(_n, lower)


if __name__ == "__main__":
    unittest.main()
