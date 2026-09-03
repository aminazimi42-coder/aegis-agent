import unittest

from app.server import create_app
from core.retry_guard import RetryGuard
from core.security import SecurityPolicy, sanitize_payload
from core.token_optimizer import TokenOptimizer
from fastapi.testclient import TestClient


class EndToEndIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_security_pipeline_blocks_threats(self):
        safe_payload = {"task": "Plan a secure global launch for the platform"}
        sanitized = sanitize_payload(safe_payload)
        self.assertEqual(sanitized["task"], "Plan a secure global launch for the platform")

        with self.assertRaises(ValueError):
            sanitize_payload({"task": "DROP TABLE users; -- system shutdown"})

        policy = SecurityPolicy()
        self.assertTrue(policy.is_allowed("Amin"))
        self.assertTrue(policy.is_allowed("Ahmad"))
        self.assertFalse(policy.is_allowed("UnknownAgent"))

    def test_token_budget_and_cache_tracking(self):
        optimizer = TokenOptimizer()
        summary = optimizer.record_usage("Plan the final release", "Alina", "Ready")

        self.assertGreater(summary["tokens_used"], 0)
        self.assertIn("total_tokens", summary)
        self.assertEqual(summary["agent_name"], "Alina")
        self.assertIsNotNone(optimizer.get_cached_response("Plan the final release"))

    def test_retry_guard_recovers_from_transient_failures(self):
        guard = RetryGuard(max_retries=2)
        attempts = {"count": 0}

        def flaky_action():
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise RuntimeError("transient failure")
            return {"status": "ok"}

        result = guard.execute("e2e-retry-task", flaky_action)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(guard.snapshot("e2e-retry-task")["status"], "healthy")

    def test_api_compatibility_and_release_readiness(self):
        health_response = self.client.get("/health")
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.json()["status"], "healthy")
        self.assertEqual(health_response.json()["version"], "1.0.0-rc1")

        metrics_response = self.client.get("/metrics")
        self.assertEqual(metrics_response.status_code, 200)
        self.assertIn("agents", metrics_response.json())

        agents_response = self.client.get("/api/v1/agents")
        self.assertEqual(agents_response.status_code, 200)
        self.assertEqual(len(agents_response.json()["agents"]), 6)

        tasks_response = self.client.get("/api/v1/tasks")
        self.assertEqual(tasks_response.status_code, 200)
        self.assertEqual(tasks_response.json()["total"], 4)

        dispatch_response = self.client.post(
            "/api/v1/tasks/dispatch",
            json={"task": "Validate the platform release and confirm final integration integrity"},
        )
        self.assertEqual(dispatch_response.status_code, 202)
        self.assertIn("task_id", dispatch_response.json())

        telemetry_response = self.client.get("/api/v1/telemetry")
        self.assertEqual(telemetry_response.status_code, 200)
        self.assertEqual(telemetry_response.json()["version"], "1.0.0-rc1")

        diagnostics_response = self.client.get("/api/v1/diagnostics")
        self.assertEqual(diagnostics_response.status_code, 200)
        self.assertTrue(diagnostics_response.json()["ready"])


if __name__ == "__main__":
    unittest.main()
