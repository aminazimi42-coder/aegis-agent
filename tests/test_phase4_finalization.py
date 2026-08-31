import unittest

from app.api.health import platform_status
from app.orchestrator import run_agent_workflow
from core.monitoring.metrics import PlatformMetrics


class PhaseFourFinalizationTests(unittest.TestCase):
    def test_platform_metrics_expose_telemetry(self):
        snapshot = PlatformMetrics().snapshot()

        self.assertIn("telemetry", snapshot)
        self.assertIn("health", snapshot["telemetry"])
        self.assertIn("security", snapshot["telemetry"])
        self.assertIn("uptime_seconds", snapshot)

    def test_orchestrator_quality_gate_passes_for_valid_workflow(self):
        payload = run_agent_workflow("Plan the launch and validate the final outcome")

        self.assertIn("quality_gate", payload)
        self.assertTrue(payload["quality_gate"]["passed"])
        self.assertIn(payload["selected_agent"], {"Alina", "Kian", "Bita", "Aylin"})

    def test_platform_status_includes_telemetry(self):
        status = platform_status()

        self.assertIn("telemetry", status)
        self.assertIn("health", status["telemetry"])


if __name__ == "__main__":
    unittest.main()
