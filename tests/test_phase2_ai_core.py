import unittest

from app.orchestrator import run_agent_workflow
from core.agent_registry import AGENT_REGISTRY
from core.ai_core import AICore


class PhaseTwoAITests(unittest.TestCase):
    def test_agent_registry_contains_four_agents(self):
        self.assertEqual(len(AGENT_REGISTRY), 4)
        self.assertEqual(
            [agent.name for agent in AGENT_REGISTRY],
            ["Alina", "Kian", "Bita", "Aylin"],
        )

    def test_ai_core_dispatches_task_to_expected_agent(self):
        core = AICore()
        result = core.dispatch("Analyze operational risk and produce a summary")

        self.assertEqual(result["agent_name"], "Bita")
        self.assertIn("summary", result["response"].lower())

    def test_orchestrator_returns_platform_payload(self):
        payload = run_agent_workflow("Plan the next system action")

        self.assertIn("platform_name", payload)
        self.assertIn("agent_count", payload)
        self.assertIn("results", payload)
        self.assertEqual(payload["agent_count"], 4)


if __name__ == "__main__":
    unittest.main()
