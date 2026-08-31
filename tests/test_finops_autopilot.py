import unittest

from app.server import create_app
from core.finops_autopilot import FinOpsAutopilot
from fastapi.testclient import TestClient


class FinOpsAutopilotTests(unittest.TestCase):
    def test_budget_enforcement_hard_caps_token_usage(self):
        controller = FinOpsAutopilot(
            tenant_daily_budget_tokens=50,
            per_request_token_cap=10,
            cost_per_1k_tokens=0.01,
        )

        with self.assertRaises(RuntimeError):
            controller.enforce_budget(
                tenant_id="tenant-a",
                task_text=(
                    "This task is deliberately oversized and should be rejected "
                    "by the hard cap."
                ),
                estimated_tokens=25,
                estimated_cost=5.0,
            )

        summary = controller.snapshot("tenant-a")
        self.assertEqual(summary["tenant_id"], "tenant-a")
        self.assertGreaterEqual(summary["remaining_tokens"], 0)

    def test_usage_tracking_and_cost_model_are_stable(self):
        controller = FinOpsAutopilot(
            tenant_daily_budget_tokens=100,
            per_request_token_cap=30,
            cost_per_1k_tokens=0.02,
        )

        usage = controller.record_usage(
            tenant_id="tenant-b",
            task_text="Plan the final rollout and validate performance metrics.",
            agent_name="Alina",
            prompt_tokens=12,
            completion_tokens=8,
        )

        self.assertEqual(usage["tenant_id"], "tenant-b")
        self.assertEqual(usage["agent_name"], "Alina")
        self.assertGreater(usage["tokens_used"], 0)
        self.assertGreater(usage["cost_usd"], 0.0)
        self.assertGreaterEqual(usage["remaining_tokens"], 0)

    def test_server_middleware_blocks_over_budget_requests(self):
        app = create_app()
        client = TestClient(app)

        response = client.post(
            "/api/v1/tasks/dispatch",
            json={
                "task": (
                    "Validate the release and monitor all agent operations under "
                    "the current spend cap."
                ),
                "tenant_id": "tenant-c",
            },
        )
        self.assertEqual(response.status_code, 202)

        over_budget_response = client.post(
            "/api/v1/tasks/dispatch",
            json={
                "task": "x" * 1200,
                "tenant_id": "tenant-c",
            },
        )
        self.assertEqual(over_budget_response.status_code, 429)


if __name__ == "__main__":
    unittest.main()
