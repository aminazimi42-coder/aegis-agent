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
        self.assertIn(
            payload["selected_agent"],
            {"Alina", "Kian", "Bita", "Aylin", "Ahmad", "Amin"},
        )

    def test_platform_status_includes_telemetry(self):
        status = platform_status()

        self.assertIn("telemetry", status)
        self.assertIn("health", status["telemetry"])

    def test_platform_metrics_include_oversight_components(self):
        snapshot = PlatformMetrics().snapshot()

        self.assertIn("oversight_components", snapshot["telemetry"])
        self.assertEqual(
            {entry["component"] for entry in snapshot["telemetry"]["oversight_components"]},
            {"amin", "ahmad"},
        )
        self.assertTrue(
            all(
                "log" in entry and entry["log"]["channel"] == "oversight"
                for entry in snapshot["telemetry"]["oversight_components"]
            )
        )

    def test_token_optimizer_tracks_budget_and_cache(self):
        from core.token_optimizer import TokenOptimizer

        optimizer = TokenOptimizer(max_tokens_per_request=100, daily_budget=500)
        cached = optimizer.cache_response("Plan the final launch", "Alina", "Plan approved")

        self.assertTrue(cached)
        self.assertEqual(optimizer.get_cached_response("Plan the final launch"), "Plan approved")
        self.assertLessEqual(optimizer.usage_summary()["total_tokens"], 500)


if __name__ == "__main__":
    unittest.main()
