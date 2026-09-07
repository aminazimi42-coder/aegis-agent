"""T93 — hash-chained local audit log for propose/approve/execute.

Verifies:
- First line ``prev_hash`` is 64 zeros.
- Second line ``prev_hash`` binds to the first line's ``hash``.
- Appending a third line does not rewrite earlier lines (append-only).
- No live network.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path


class TestT93AuditChain(unittest.TestCase):
    """Hash-chained append-only audit log under data_root/tenant/audit.jsonl."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _audit_path(self, tenant_id: str = "t93") -> Path:
        return Path(self._tmp) / tenant_id / "audit.jsonl"

    def _lines(self, tenant_id: str = "t93") -> list[dict]:
        path = self._audit_path(tenant_id)
        text = path.read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_first_line_zero_prev(self) -> None:
        """First appended line has prev_hash = 64 zeros."""
        from core.twin_audit import append_audit

        h = append_audit("t93", "propose", "act-aaa")
        lines = self._lines()
        self.assertEqual(len(lines), 1)
        first = lines[0]
        self.assertEqual(first["prev_hash"], "0" * 64)
        self.assertEqual(len(first["prev_hash"]), 64)
        self.assertEqual(first["hash"], h)
        self.assertEqual(first["kind"], "propose")
        self.assertEqual(first["action_id"], "act-aaa")

    def test_second_line_binds_prev(self) -> None:
        """Second line's prev_hash equals the first line's hash."""
        from core.twin_audit import append_audit

        append_audit("t93", "propose", "act-aaa")
        append_audit("t93", "approve", "act-aaa")
        lines = self._lines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[1]["prev_hash"], lines[0]["hash"])
        self.assertEqual(lines[1]["kind"], "approve")

    def test_rewrite_forbidden_or_detectable(self) -> None:
        """Appending a third line does not rewrite earlier lines."""
        from core.twin_audit import append_audit

        append_audit("t93", "propose", "act-aaa")
        append_audit("t93", "approve", "act-aaa")
        first_two = self._lines()

        append_audit("t93", "execute", "act-aaa")
        lines = self._lines()
        self.assertEqual(len(lines), 3)
        # First two lines unchanged (append-only, never rewritten).
        self.assertEqual(lines[0], first_two[0])
        self.assertEqual(lines[1], first_two[1])
        # Chain still valid: third prev_hash == second hash.
        self.assertEqual(lines[2]["prev_hash"], lines[1]["hash"])
        self.assertEqual(lines[2]["kind"], "execute")


if __name__ == "__main__":
    unittest.main()
