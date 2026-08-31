import unittest

from core.router import SmartModelRouter
from core.schemas import AgentResponse
from pydantic import ValidationError


class SmartModelRouterTests(unittest.TestCase):
    def test_agent_response_schema_rejects_incomplete_payload(self):
        with self.assertRaises(ValidationError):
            AgentResponse.model_validate({
                "agent_name": "Alina",
                "response": "Strategy response",
            })

    def test_router_retries_and_recovers_from_invalid_schema(self):
        calls = {"count": 0}

        def factory(task: str, model_name: str | None = None):
            calls["count"] += 1
            if calls["count"] == 1:
                return {
                    "agent_name": "Alina",
                    "response": "Strategic plan",
                    "task": task,
                }
            return {
                "agent_name": "Alina",
                "role": "Strategic coordination",
                "response": "Strategic plan",
                "task": task,
                "status": "completed",
                "model": model_name or "alina",
            }

        router = SmartModelRouter(max_retries=2)
        result = router.route("Plan the deployment", factory=factory)

        self.assertEqual(calls["count"], 2)
        self.assertEqual(result.agent_name, "Alina")
        self.assertEqual(result.status, "completed")

    def test_router_raises_after_retry_budget_is_exhausted(self):
        calls = {"count": 0}

        def factory(task: str, model_name: str | None = None):
            calls["count"] += 1
            return {
                "agent_name": "Alina",
                "response": "Bad output",
                "task": task,
            }

        router = SmartModelRouter(max_retries=2)

        with self.assertRaises(ValueError):
            router.route("Validate the final release", factory=factory)

        self.assertEqual(calls["count"], 3)


if __name__ == "__main__":
    unittest.main()
