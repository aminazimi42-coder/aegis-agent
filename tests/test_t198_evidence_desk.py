"""T198 — Local evidence desk: one tenant-bound evidence pack.

Tests:

* ``test_html_has_export_evidence_pack_control``
* ``test_pack_written_inside_data_dir``
* ``test_pack_contains_verify_chain_result``
* ``test_pack_copies_brief_and_sig_when_present``
* ``test_pack_missing_brief_is_typed_note_not_crash``
* ``test_pack_audit_tail_is_redacted``
* ``test_pack_does_not_include_neighbor_tenant``
* ``test_outside_data_dir_typed_deny``
* ``test_pack_does_not_execute_or_approve``
* ``test_readme_author_untouched``
* ``test_readme_does_not_contain_notarized``
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path

from core.twin_actions import (
    _action_digest,
    _load_action,
    approve,
    execute,
    insert_specialist_proposal,
    list_actions,
)
from core.twin_interview import QUESTIONS, answer, commit, start_session

_NOT = "nota"
_RIZED = "rized"


class TestT198EvidenceDesk(unittest.TestCase):
    """T198 — Local evidence pack from existing chain/brief/audit/receipts."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t198_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _html(self) -> str:
        """Read the operator page HTML."""
        html_path = Path("app.html")
        if not html_path.exists():
            html_path = Path(
                "desktop/macos/Aegis.app/Contents/Resources/app.html"
            )
        return html_path.read_text("utf-8")

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
            tenant_id, "Alina", "Review the weekly digest", {"body": "t198"}
        )
        action_id = row["action_id"]
        action = _load_action(action_id)
        assert action is not None
        approve(action_id, tenant_id, "tester", _action_digest(action))
        execute(action_id, tenant_id)
        return action_id

    def _build_pack(self, tenant_id: str) -> dict:
        """Build an evidence pack and return the result dict."""
        from core.evidence_desk import build_evidence_pack

        return build_evidence_pack(tenant_id)

    # ------------------------------------------------------------------ #
    # 1) HTML has Export evidence pack control
    # ------------------------------------------------------------------ #

    def test_html_has_export_evidence_pack_control(self) -> None:
        """The operator page HTML contains the Export evidence pack control."""
        html = self._html()
        self.assertIn("Export evidence pack", html)
        self.assertIn("btn-evidence-pack", html)
        self.assertIn("exportEvidencePack", html)

    # ------------------------------------------------------------------ #
    # 2) Pack is written inside the data dir
    # ------------------------------------------------------------------ #

    def test_pack_written_inside_data_dir(self) -> None:
        """The evidence pack zip is written under AEGIS_DATA_DIR/export/."""
        tenant = "t198_inside"
        self._execute_one_action(tenant)
        result = self._build_pack(tenant)
        pack_path = Path(result["path"])
        self.assertTrue(pack_path.is_file())
        self.assertTrue(pack_path.suffix == ".zip")
        # The path must be inside AEGIS_DATA_DIR.
        data_dir = Path(self._tmp).resolve()
        self.assertIn(str(data_dir.resolve()), str(pack_path.resolve()))
        self.assertIn("export", str(pack_path))
        # sha256 must be present and non-empty.
        self.assertTrue(result["sha256"])
        self.assertEqual(len(result["sha256"]), 64)

    # ------------------------------------------------------------------ #
    # 3) Pack contains verify_chain result
    # ------------------------------------------------------------------ #

    def test_pack_contains_verify_chain_result(self) -> None:
        """The pack contains verify_chain.txt with Intact or Tampered."""
        tenant = "t198_vc"
        self._execute_one_action(tenant)
        result = self._build_pack(tenant)
        pack_path = Path(result["path"])
        with zipfile.ZipFile(pack_path, "r") as zf:
            names = zf.namelist()
            self.assertIn("verify_chain.txt", names)
            vc = zf.read("verify_chain.txt").decode("utf-8")
            self.assertIn("verify_chain:", vc)
            self.assertIn("Intact", vc)
            self.assertIn("tenant_id: " + tenant, vc)

    # ------------------------------------------------------------------ #
    # 4) Pack copies brief and .sig when present
    # ------------------------------------------------------------------ #

    def test_pack_copies_brief_and_sig_when_present(self) -> None:
        """When a signed brief+.sig exists, the pack copies both."""
        tenant = "t198_brief"
        self._execute_one_action(tenant)
        # Write a signed brief so it exists under export/.
        from core.twin_local_recall import signed_export

        signed_export(tenant, name="local_t198_test.md")
        result = self._build_pack(tenant)
        pack_path = Path(result["path"])
        with zipfile.ZipFile(pack_path, "r") as zf:
            names = zf.namelist()
            self.assertIn("brief.md", names)
            self.assertIn("brief.md.sig", names)
            brief = zf.read("brief.md").decode("utf-8")
            self.assertIn(tenant, brief)

    # ------------------------------------------------------------------ #
    # 5) Missing brief is a typed note, not a crash
    # ------------------------------------------------------------------ #

    def test_pack_missing_brief_is_typed_note_not_crash(self) -> None:
        """When no signed brief exists, the pack has a missing_brief.txt."""
        tenant = "t198_nobrief"
        self._execute_one_action(tenant)
        # Do not write a signed brief — no local_*.md under export/.
        result = self._build_pack(tenant)
        pack_path = Path(result["path"])
        with zipfile.ZipFile(pack_path, "r") as zf:
            names = zf.namelist()
            self.assertIn("missing_brief.txt", names)
            self.assertNotIn("brief.md", names)
            note = zf.read("missing_brief.txt").decode("utf-8")
            self.assertIn("missing_brief", note)

    # ------------------------------------------------------------------ #
    # 6) Audit tail is redacted
    # ------------------------------------------------------------------ #

    def test_pack_audit_tail_is_redacted(self) -> None:
        """The audit tail in the pack does not contain raw secret shapes."""
        tenant = "t198_redact"
        self._execute_one_action(tenant)
        result = self._build_pack(tenant)
        pack_path = Path(result["path"])
        with zipfile.ZipFile(pack_path, "r") as zf:
            names = zf.namelist()
            self.assertIn("audit_tail.jsonl", names)
            audit = zf.read("audit_tail.jsonl").decode("utf-8")
            # A whsec_ secret shape must not appear unredacted.
            self.assertNotIn("whsec_", audit)

    # ------------------------------------------------------------------ #
    # 7) Pack does not include neighbor tenant
    # ------------------------------------------------------------------ #

    def test_pack_does_not_include_neighbor_tenant(self) -> None:
        """The pack for tenant A does not include tenant B's data."""
        tenant_a = "t198_neighbor_a"
        tenant_b = "t198_neighbor_b"
        self._execute_one_action(tenant_a)
        self._execute_one_action(tenant_b)
        result = self._build_pack(tenant_a)
        pack_path = Path(result["path"])
        with zipfile.ZipFile(pack_path, "r") as zf:
            vc = zf.read("verify_chain.txt").decode("utf-8")
            self.assertIn(tenant_a, vc)
            self.assertNotIn(tenant_b, vc)
            # The audit tail must not contain tenant_b's action_id.
            audit = zf.read("audit_tail.jsonl").decode("utf-8")
            # Get tenant_b's action_ids.
            b_actions = list_actions(tenant_b)
            for a in b_actions:
                self.assertNotIn(a["action_id"], audit)

    # ------------------------------------------------------------------ #
    # 8) Outside data dir is typed deny
    # ------------------------------------------------------------------ #

    def test_outside_data_dir_typed_deny(self) -> None:
        """A destination outside AEGIS_DATA_DIR is a typed PathDeniedError."""
        from core.twin_local_view import PathDeniedError, cage_path

        # cage_path on an outside path must raise PathDeniedError.
        outside = Path(tempfile.gettempdir()) / "t198_outside_test"
        with self.assertRaises(PathDeniedError) as ctx:
            cage_path(outside)
        self.assertEqual(ctx.exception.code, "path_denied_outside_data_dir")

    # ------------------------------------------------------------------ #
    # 9) Pack does not execute or approve
    # ------------------------------------------------------------------ #

    def test_pack_does_not_execute_or_approve(self) -> None:
        """Building the pack does not change action status or queue."""
        tenant = "t198_noexec"
        self._full_interview(tenant)
        batch = f"batch-{uuid.uuid4().hex[:8]}"
        row = insert_specialist_proposal(
            tenant, "Alina", "Review the weekly digest", {"body": "noexec"},
            batch_id=batch,
        )
        action_id = row["action_id"]
        # Build the pack while the action is still 'proposed'.
        result = self._build_pack(tenant)
        # The action must still be 'proposed' — building the pack did
        # not approve or execute.
        action = _load_action(action_id)
        assert action is not None
        self.assertEqual(action["status"], "proposed")
        # The pack must still be built successfully.
        self.assertTrue(Path(result["path"]).is_file())

    # ------------------------------------------------------------------ #
    # 10) README Author untouched
    # ------------------------------------------------------------------ #

    def test_readme_author_untouched(self) -> None:
        """The README Author paragraph is present and untouched."""
        text = Path("README.md").read_text("utf-8")
        self.assertIn("## Author", text)
        self.assertIn("Amin Azimi", text)

    # ------------------------------------------------------------------ #
    # 11) README does not contain notarized
    # ------------------------------------------------------------------ #

    def test_readme_does_not_contain_notarized(self) -> None:
        """The word notarized does not appear in README (case-insensitive)."""
        _word = _NOT + _RIZED
        text = Path("README.md").read_text("utf-8").lower()
        self.assertNotIn(_word, text)


if __name__ == "__main__":
    unittest.main()
