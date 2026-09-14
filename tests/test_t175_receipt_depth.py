"""T175 — Receipt depth: correlation id, note hash, digest preview, Intact/Tampered.

Covers:

* A propose writes a local ``correlation_id`` on the action row.
* Approve, receipt, and audit all share the same ``correlation_id``.
* When an approve note exists, its SHA-256 hash enters the receipt chain.
* An empty note still chains (no ``note_hash`` line, body still hashes).
* The operator page shows a digest preview before Approve.
* ``verify_chain`` returns ``Intact`` when hashes match, ``Tampered`` when not.
* A neighbor tenant cannot read another tenant's correlation id.
* The README Author paragraph is untouched.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.audit_logger import get_correlation_id, read_events
from core.twin_actions import (
    _action_digest,
    _load_action,
    approve,
    execute,
    insert_specialist_proposal,
    verify_chain,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session


class TestT175ReceiptDepth(unittest.TestCase):
    """Receipt depth: correlation id, note hash, digest preview, Intact/Tampered."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t175_")
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
    # 1) Correlation id
    # ------------------------------------------------------------------ #

    def test_propose_writes_correlation_id(self) -> None:
        """insert_specialist_proposal mints and persists a correlation_id."""
        tenant = "t175_corr"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Review the weekly digest", {"body": "check"}
        )
        self.assertIn("correlation_id", row)
        self.assertTrue(row["correlation_id"])
        # The correlation_id must also be in the DB row.
        action = _load_action(row["action_id"])
        assert action is not None
        self.assertEqual(action["correlation_id"], row["correlation_id"])
        # The audit map must have it.
        self.assertEqual(
            get_correlation_id(row["action_id"]), row["correlation_id"]
        )

    def test_approve_receipt_and_audit_share_correlation_id(self) -> None:
        """Approve, receipt, and audit all share the same correlation_id."""
        tenant = "t175_share"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Review the weekly digest", {"body": "approve me"}
        )
        action_id = row["action_id"]
        cid = row["correlation_id"]

        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action), why="good note")
        executed = execute(action_id, tenant)
        self.assertEqual(executed["status"], "executed")

        # The receipt body does not directly carry correlation_id, but the
        # audit line does.
        events = read_events()
        approve_events = [e for e in events if e.get("kind") == "approve"]
        self.assertTrue(any(e.get("correlation_id") == cid for e in approve_events))
        exec_events = [e for e in events if e.get("kind") == "execute"]
        self.assertTrue(any(e.get("correlation_id") == cid for e in exec_events))
        propose_events = [e for e in events if e.get("kind") == "propose"]
        self.assertTrue(any(e.get("correlation_id") == cid for e in propose_events))

    # ------------------------------------------------------------------ #
    # 2) Note hash in chain
    # ------------------------------------------------------------------ #

    def test_note_hash_enters_chain_when_note_present(self) -> None:
        """When an approve note exists, its hash enters the receipt chain."""
        import hashlib

        tenant = "t175_notehash"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Review the weekly digest", {"body": "note test"}
        )
        action_id = row["action_id"]
        note = "approved with a reason"
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action), why=note)
        execute(action_id, tenant)

        receipt_text = self._receipt_path(tenant, action_id).read_text("utf-8")
        expected_hash = hashlib.sha256(note.encode("utf-8")).hexdigest()
        self.assertIn(f"note_hash: {expected_hash}", receipt_text)

    def test_empty_note_still_chains(self) -> None:
        """An empty approve note still produces a valid receipt chain."""
        tenant = "t175_emptynote"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Review the weekly digest", {"body": "empty note test"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action))
        execute(action_id, tenant)

        receipt_text = self._receipt_path(tenant, action_id).read_text("utf-8")
        self.assertNotIn("note_hash:", receipt_text)
        # The receipt_sha must still be present and valid.
        self.assertIn("receipt_sha:", receipt_text)

    # ------------------------------------------------------------------ #
    # 3) Digest preview
    # ------------------------------------------------------------------ #

    def test_digest_preview_on_operator_page(self) -> None:
        """The operator page JS includes a digest preview element."""
        html_path = Path("app.html")
        if not html_path.exists():
            html_path = Path(
                "desktop/macos/Aegis.app/Contents/Resources/app.html"
            )
        html = html_path.read_text("utf-8")
        self.assertIn("digest preview", html)

    # ------------------------------------------------------------------ #
    # 4) Intact / Tampered
    # ------------------------------------------------------------------ #

    def test_verify_chain_intact(self) -> None:
        """verify_chain returns Intact for a valid receipt."""
        tenant = "t175_intact"
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

    def test_verify_chain_tampered(self) -> None:
        """verify_chain returns Tampered when the receipt body is modified."""
        tenant = "t175_tampered"
        self._full_interview(tenant)
        row = insert_specialist_proposal(
            tenant, "Alina", "Review the weekly digest", {"body": "tamper test"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant, "tester", _action_digest(action))
        execute(action_id, tenant)

        # Tamper with the receipt file.
        receipt_path = self._receipt_path(tenant, action_id)
        original = receipt_path.read_text("utf-8")
        tampered = original.replace("title: Review the weekly digest", "title: HACKED")
        receipt_path.write_text(tampered, "utf-8")

        self.assertEqual(verify_chain(tenant, action_id), "Tampered")

    # ------------------------------------------------------------------ #
    # 5) Neighbor tenant isolation
    # ------------------------------------------------------------------ #

    def test_neighbor_cannot_read_correlation(self) -> None:
        """A neighbor tenant cannot read another tenant's correlation_id."""
        tenant_a = "t175_neighbor_a"
        tenant_b = "t175_neighbor_b"
        self._full_interview(tenant_a)
        self._full_interview(tenant_b)

        row_a = insert_specialist_proposal(
            tenant_a, "Alina", "Review the weekly digest", {"body": "tenant a"}
        )
        row_b = insert_specialist_proposal(
            tenant_b, "Alina", "Review the weekly digest", {"body": "tenant b"}
        )

        # Each tenant's action has its own correlation_id.
        self.assertNotEqual(
            row_a["correlation_id"], row_b["correlation_id"]
        )

        # Tenant B cannot list tenant A's actions.
        from core.twin_actions import list_actions

        actions_b = list_actions(tenant_b)
        action_ids_b = {a["action_id"] for a in actions_b}
        self.assertNotIn(row_a["action_id"], action_ids_b)

    # ------------------------------------------------------------------ #
    # 6) README Author untouched
    # ------------------------------------------------------------------ #

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and untouched."""
        from pathlib import Path as P

        text = P("README.md").read_text("utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)


if __name__ == "__main__":
    unittest.main()
