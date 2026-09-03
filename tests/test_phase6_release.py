import unittest

from app.health import health_snapshot
from app.orchestrator import run_agent_workflow
from core.config import load_config


class PhaseSixReleaseTests(unittest.TestCase):
    def test_release_configuration_is_valid(self):
        config = load_config({"environment": "production", "version": "1.0.0-rc1"})

        self.assertEqual(config.environment, "production")
        self.assertEqual(config.version, "1.0.0-rc1")
        self.assertEqual(config.agent_count, 6)

    def test_release_status_is_healthy(self):
        snapshot = health_snapshot()

        self.assertEqual(snapshot["status"], "healthy")
        self.assertEqual(snapshot["service"], "Aegis Agent Platform")

    def test_release_workflow_remains_operational(self):
        workflow = run_agent_workflow(
            "Deploy the platform to production and validate release quality"
        )

        self.assertEqual(workflow["agent_count"], 6)
        self.assertEqual(len(workflow["results"]), 6)
        self.assertEqual(
            {item["agent_name"] for item in workflow["results"]},
            {"Alina", "Kian", "Bita", "Aylin", "Ahmad", "Amin"},
        )


if __name__ == "__main__":
    unittest.main()
