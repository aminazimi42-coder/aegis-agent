import unittest

from core.model_router import TrustAwareModelRouter


class TrustAwareModelRouterTests(unittest.TestCase):
    def test_router_selects_model_based_on_task_signal(self):
        router = TrustAwareModelRouter()

        self.assertEqual(router.decide_model("Plan the launch and coordinate strategy"), "Alina")
        self.assertEqual(router.decide_model("Deploy the platform and monitor runtime"), "Kian")
        self.assertEqual(router.decide_model("Analyze the risk profile and synthesize insight"), "Bita")
        self.assertEqual(router.decide_model("Validate the release and audit the final state"), "Aylin")

    def test_router_includes_cost_and_latency_metadata(self):
        router = TrustAwareModelRouter()
        decision = router.evaluate("Plan the rollout and validate privacy-safe execution")

        self.assertIn("selected_model", decision)
        self.assertIn("cost_score", decision)
        self.assertIn("latency_score", decision)
        self.assertIn("privacy_score", decision)
        self.assertIn("capability_score", decision)

    def test_router_rejects_invalid_payloads_after_retry_budget(self):
        router = TrustAwareModelRouter(max_retries=1)

        def factory(task: str, model_name: str | None = None):
            return {"agent_name": "Alina", "response": "Bad output", "task": task}

        with self.assertRaises(ValueError):
            router.route("Validate the final release", factory=factory)


if __name__ == "__main__":
    unittest.main()
