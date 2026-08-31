import unittest

from app.health import health_snapshot
from app.orchestrator import run_agent_workflow
from core.ai_core import AICore


class PhaseFiveIntegrationTests(unittest.TestCase):
    def test_end_to_end_task_flow(self):
        task = "Plan execution for a global release and validate the final outcome"
        workflow = run_agent_workflow(task)

        self.assertEqual(workflow["agent_count"], 4)
        self.assertEqual(len(workflow["results"]), 4)
        self.assertEqual(
            {item["agent_name"] for item in workflow["results"]},
            {"Alina", "Kian", "Bita", "Aylin"},
        )

    def test_ai_core_integration_works_across_all_agents(self):
        core = AICore()
        results = core.run_workflow("Analyze operational risk and confirm quality")

        self.assertEqual(len(results), 4)
        self.assertIn("role", results[0])
        self.assertIn("response", results[0])

    def test_platform_health_remains_healthy(self):
        snapshot = health_snapshot()

        self.assertEqual(snapshot["status"], "healthy")
        self.assertEqual(snapshot["agent_count"], 4)


if __name__ == "__main__":
    unittest.main()
