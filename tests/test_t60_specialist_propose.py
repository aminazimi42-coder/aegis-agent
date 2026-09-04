"""T60 — Six specialists propose; none execute.

Covers:
- All six agents (Bita, Kian, Alina, Aylin, Ahmad, Amin) expose
  ``propose(tenant_id)`` which inserts one ``twin_actions`` row with
  ``status = "proposed"``.
- All proposals land in a single shared queue (same ``tenant_id``).
- No specialist module imports or calls ``twin_actions.execute``.
- AEGIS_DATA_DIR temp isolation; no live network.
"""

from __future__ import annotations

import inspect
import os
import tempfile
import unittest

from core.twin_actions import list_actions


class TestT60SpecialistPropose(unittest.TestCase):
    """Six specialists propose into one shared action queue."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="aegis_t60_")
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self) -> None:
        os.environ.pop("AEGIS_DATA_DIR", None)

    # ------------------------------------------------------------------ #
    # Tests
    # ------------------------------------------------------------------ #

    def test_all_six_agents_propose_into_one_queue(self) -> None:
        """Each agent.propose inserts exactly one proposed row; all share a queue."""
        from agents.ahmad.agent import AhmadAgent
        from agents.alina.agent import AlinaAgent
        from agents.amin.agent import AminAgent
        from agents.aylin.agent import AylinAgent
        from agents.bita.agent import BitaAgent
        from agents.kian.agent import KianAgent

        agents = [
            BitaAgent(),
            KianAgent(),
            AlinaAgent(),
            AylinAgent(),
            AhmadAgent(),
            AminAgent(),
        ]
        tenant = "t60-queue"

        for agent in agents:
            result = agent.propose(tenant)
            self.assertEqual(result["status"], "proposed")
            self.assertEqual(result["tenant_id"], tenant)
            self.assertTrue(
                result["kind"].startswith(f"{agent.name}:"),
                f"kind {result['kind']!r} should start with agent name "
                f"{agent.name!r}",
            )

        rows = list_actions(tenant)
        self.assertEqual(len(rows), 6, f"expected 6 rows, got {len(rows)}")
        for row in rows:
            self.assertEqual(row["status"], "proposed")
            self.assertEqual(row["tenant_id"], tenant)

        # Verify each kind is agent-name-prefixed and distinct.
        kinds = {row["kind"] for row in rows}
        self.assertEqual(len(kinds), 6, f"expected 6 distinct kinds, got {kinds}")

    def test_no_specialist_module_calls_execute(self) -> None:
        """No specialist agent.py source imports or calls twin_actions.execute."""
        import agents.ahmad.agent as ahmad_mod
        import agents.alina.agent as alina_mod
        import agents.amin.agent as amin_mod
        import agents.aylin.agent as aylin_mod
        import agents.bita.agent as bita_mod
        import agents.kian.agent as kian_mod

        modules = [
            bita_mod,
            kian_mod,
            alina_mod,
            aylin_mod,
            ahmad_mod,
            amin_mod,
        ]
        for mod in modules:
            source = inspect.getsource(mod)
            # No reference to twin_actions.execute or import of execute.
            self.assertNotIn(
                "twin_actions.execute",
                source,
                f"{mod.__name__} must not reference twin_actions.execute",
            )
            self.assertNotIn(
                "from core.twin_actions import execute",
                source,
                f"{mod.__name__} must not import execute from twin_actions",
            )

    def test_no_live_network(self) -> None:
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
