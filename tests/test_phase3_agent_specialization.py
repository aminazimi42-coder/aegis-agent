import unittest

from agents.alina.agent import AlinaAgent
from agents.aylin.agent import AylinAgent
from agents.bita.agent import BitaAgent
from agents.kiyan.agent import KiyanAgent
from app.orchestrator import run_agent_workflow


class PhaseThreeAgentSpecializationTests(unittest.TestCase):
    def test_agents_expose_role_metadata(self):
        self.assertEqual(AlinaAgent().profile()["role"], "Strategic coordination")
        self.assertEqual(KiyanAgent().profile()["role"], "Operational execution")
        self.assertEqual(BitaAgent().profile()["role"], "Analysis and synthesis")
        self.assertEqual(AylinAgent().profile()["role"], "Quality and validation")

    def test_orchestrator_runs_all_four_agents(self):
        payload = run_agent_workflow(
            "Plan execution for a new deployment and validate the final output"
        )

        self.assertEqual(payload["agent_count"], 4)
        self.assertEqual(len(payload["results"]), 4)
        self.assertEqual(
            {item["agent_name"] for item in payload["results"]},
            {"Alina", "Kiyan", "Bita", "Aylin"},
        )

    def test_agent_response_has_specialized_context(self):
        self.assertIn("strategy", AlinaAgent().handle("Plan the new strategy").lower())
        self.assertIn("execution", KiyanAgent().handle("Execute the new deployment").lower())
        self.assertIn("analysis", BitaAgent().handle("Analyze the risks").lower())
        self.assertIn("validation", AylinAgent().handle("Validate the outcome").lower())


if __name__ == "__main__":
    unittest.main()
