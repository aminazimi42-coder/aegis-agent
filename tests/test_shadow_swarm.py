import unittest

from core.shadow_swarm import ShadowSwarmRunner


class ShadowSwarmTests(unittest.TestCase):
    def test_shadow_runner_basic_consensus(self):
        runner = ShadowSwarmRunner()
        result = runner.execute_and_compare("Plan the deployment")
        self.assertIn("primary", result.__dict__)
        self.assertIn("shadow", result.__dict__)
        self.assertIsInstance(result.divergence_score, float)
        self.assertIn("agent_name", result.primary)
        self.assertIn("agent_name", result.shadow)

    def test_shadow_runner_custom_modifier(self):
        runner = ShadowSwarmRunner()

        def modifier(task: str) -> str:
            return task + " with altered constraints"

        result = runner.execute_and_compare("Analyze risk", shadow_modifier=modifier)
        self.assertIsInstance(result.divergence_score, float)
        self.assertIn("elapsed_ms", result.details)


if __name__ == "__main__":
    unittest.main()
