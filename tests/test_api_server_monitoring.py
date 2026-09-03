import os
import tempfile
import unittest

from app.server import create_app
from fastapi.testclient import TestClient


class PhaseTwoAPITests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp
        self.app = create_app()
        self.client = TestClient(self.app)

    def tearDown(self):
        del os.environ["AEGIS_DATA_DIR"]

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "healthy")
        self.assertEqual(payload["service"], "Aegis Agent Platform")

    def test_metrics_endpoint(self):
        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("agents", payload)
        self.assertIn("uptime_seconds", payload)

    def test_agent_catalog_endpoint(self):
        response = self.client.get("/api/v1/agents")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["agents"]), 6)
        self.assertEqual(
            {item["name"] for item in payload["agents"]},
            {"Alina", "Kian", "Bita", "Aylin", "Ahmad", "Amin"},
        )

    def test_task_dispatch_endpoint(self):
        response = self.client.post(
            "/api/v1/tasks/dispatch",
            json={"task": "Plan a global launch and validate the final outcome"},
        )
        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertIn("task_id", payload)
        self.assertIn("status", payload)
        self.assertEqual(payload["status"], "queued")
        self.assertIn("duplicate", payload)

    def test_task_status_lookup_endpoint(self):
        create_response = self.client.post(
            "/api/v1/tasks/dispatch",
            json={"task": "Validate release readiness and audit the final state"},
        )
        task_id = create_response.json()["task_id"]

        response = self.client.get(f"/api/v1/tasks/{task_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task_id"], task_id)
        self.assertIn("status", payload)
        self.assertIn("telemetry", payload)


if __name__ == "__main__":
    unittest.main()
