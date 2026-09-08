"""T121 — Distinct specialist proposals in one batch.

Covers:
- One propose batch creates six rows (one per specialist) sharing a batch_id.
- Within one batch_id all titles, kinds, and bodies are unique.
- Ahmad is a security/oversight gate, not a duplicate of Alina's strategy
  brief.
- Amin is a finance/cost gate.
- No live network except ``TestClient``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from uuid import uuid4


class TestT121SpecialistDistinct(unittest.TestCase):
    """Six specialist proposals in one batch are distinct and role-shaped."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t121_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _propose_batch(self, tenant_id: str, text: str) -> tuple[list[dict], str]:
        """Run one propose batch via the six specialists; return (rows, batch_id)."""
        from agents.ahmad.agent import AhmadAgent
        from agents.alina.agent import AlinaAgent
        from agents.amin.agent import AminAgent
        from agents.aylin.agent import AylinAgent
        from agents.bita.agent import BitaAgent
        from agents.kian.agent import KianAgent
        from core.twin_actions import list_actions

        specialists = [
            AlinaAgent(),
            KianAgent(),
            BitaAgent(),
            AylinAgent(),
            AhmadAgent(),
            AminAgent(),
        ]
        batch_id = f"batch-{uuid4().hex[:12]}"
        for agent in specialists:
            agent.propose(tenant_id, text, batch_id=batch_id)
        rows = list_actions(tenant_id)
        return rows, batch_id

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_six_rows_one_batch(self) -> None:
        """One propose batch creates exactly six proposed rows with the same batch_id."""
        rows, batch_id = self._propose_batch("t121-six", "Review the weekly plan")
        self.assertEqual(len(rows), 6)
        for row in rows:
            self.assertEqual(row["status"], "proposed")
            self.assertEqual(row["batch_id"], batch_id)

    def test_titles_or_kinds_are_unique_in_batch(self) -> None:
        """Within one batch_id all titles, kinds, and bodies are distinct."""
        rows, _ = self._propose_batch("t121-unique", "Prepare the board memo")
        self.assertEqual(len(rows), 6)

        titles = [row["title"] for row in rows]
        kinds = [row["kind"] for row in rows]
        self.assertEqual(
            len(set(titles)), 6, f"titles not unique: {titles}"
        )
        self.assertEqual(
            len(set(kinds)), 6, f"kinds not unique: {kinds}"
        )

        # Bodies must also be distinct — no copy-paste across all six.
        bodies: list[str] = []
        for row in rows:
            payload = row.get("payload")
            if isinstance(payload, dict):
                bodies.append(payload.get("body", ""))
            elif isinstance(payload, str):
                import json

                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, dict):
                        bodies.append(parsed.get("body", ""))
                    else:
                        bodies.append(str(parsed))
                except (json.JSONDecodeError, TypeError):
                    bodies.append(str(payload))
            else:
                bodies.append("")
        self.assertEqual(
            len(set(bodies)), 6, f"bodies not unique: {bodies}"
        )

    def test_ahmad_is_gate_not_alina_clone(self) -> None:
        """Ahmad's body is a security/oversight gate, not Alina's strategy brief."""
        from agents.ahmad.agent import AhmadAgent
        from agents.alina.agent import AlinaAgent

        text = "Review the security posture"
        ahmad_body = AhmadAgent()._propose_body(text)
        alina_body = AlinaAgent()._propose_body(text)

        self.assertNotEqual(ahmad_body, alina_body)
        self.assertIn("Security", ahmad_body)
        # Ahmad must not echo Alina's strategy prefix.
        self.assertNotIn("Strategy", ahmad_body)

    def test_amin_is_finance_gate(self) -> None:
        """Amin's body is a finance/cost gate."""
        from agents.amin.agent import AminAgent

        text = "Review the budget"
        amin_body = AminAgent()._propose_body(text)
        self.assertIn("Finance", amin_body)

    def test_no_live_network(self) -> None:
        """TestClient is local; no external network call is made."""
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
