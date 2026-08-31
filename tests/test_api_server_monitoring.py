import unittest

from app.server import create_app
from fastapi.testclient import TestClient


class PhaseTwoAPITests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = TestClient(self.app)

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
        self.assertEqual(len(payload["agents"]), 4)
        self.assertEqual(
            {item["name"] for item in payload["agents"]},
            {"Alina", "Kian", "Bita", "Aylin"},
        )

    def test_task_dispatch_endpoint(self):
        response = self.client.post(
            "/api/v1/tasks/dispatch",
            json={"task": "Plan a global launch and validate the final outcome"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("selected_agent", payload)
        self.assertIn("results", payload)


if __name__ == "__main__":
    unittest.main()
