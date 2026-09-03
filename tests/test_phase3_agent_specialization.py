import unittest

from agents.ahmad.agent import AhmadAgent
from agents.alina.agent import AlinaAgent
from agents.amin.agent import AminAgent
from agents.aylin.agent import AylinAgent
from agents.bita.agent import BitaAgent
from agents.kian.agent import KianAgent
from app.orchestrator import run_agent_workflow


class PhaseThreeAgentSpecializationTests(unittest.TestCase):
    def test_agents_expose_role_metadata(self):
        self.assertEqual(AlinaAgent().profile()["role"], "Strategic coordination")
        self.assertEqual(KianAgent().profile()["role"], "Operational execution")
        self.assertEqual(BitaAgent().profile()["role"], "Analysis and synthesis")
        self.assertEqual(AylinAgent().profile()["role"], "Quality and validation")
        self.assertEqual(AhmadAgent().profile()["role"], "Security and oversight")
        self.assertEqual(AminAgent().profile()["role"], "Finance and executive bridge")

    def test_orchestrator_runs_all_six_agents(self):
        payload = run_agent_workflow(
            "Plan execution for a new deployment and validate the final output"
        )

        self.assertEqual(payload["agent_count"], 6)
        self.assertEqual(len(payload["results"]), 6)
        self.assertEqual(
            {item["agent_name"] for item in payload["results"]},
            {"Alina", "Kian", "Bita", "Aylin", "Ahmad", "Amin"},
        )

    def test_agent_response_has_specialized_context(self):
        self.assertIn("strategy", AlinaAgent().handle("Plan the new strategy").lower())
        self.assertIn("execution", KianAgent().handle("Execute the new deployment").lower())
        self.assertIn("analysis", BitaAgent().handle("Analyze the risks").lower())
        self.assertIn("validation", AylinAgent().handle("Validate the outcome").lower())
        self.assertIn("governance", AhmadAgent().handle("Review the security posture").lower())
        self.assertIn("financial", AminAgent().handle("Settle the invoice budget").lower())


if __name__ == "__main__":
    unittest.main()
