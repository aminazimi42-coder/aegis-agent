import unittest

from app.server import create_app
from fastapi.testclient import TestClient


class OpenAPIRouteExpansionTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_openapi_contains_expanded_route_set(self):
        payload = self.client.get("/openapi.json").json()
        paths = set(payload["paths"])

        self.assertIn("/health", paths)
        self.assertIn("/metrics", paths)
        self.assertIn("/api/v1/agents", paths)
        self.assertIn("/api/v1/agents/{agent_name}", paths)
        self.assertIn("/api/v1/tasks", paths)
        self.assertIn("/api/v1/tasks/dispatch", paths)
        self.assertIn("/api/v1/telemetry", paths)
        self.assertIn("/api/v1/diagnostics", paths)

    def test_expanded_routes_return_valid_payloads(self):
        agent_path = "/api/v1/agents/{agent_name}".replace("{agent_name}", "Alina")
        self.assertEqual(self.client.get(agent_path).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/telemetry").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/diagnostics").status_code, 200)


if __name__ == "__main__":
    unittest.main()
