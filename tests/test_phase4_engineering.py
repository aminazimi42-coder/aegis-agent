import unittest

from app.health import HealthStatus, health_snapshot
from core.config import load_config
from core.security import SecurityPolicy


class PhaseFourEngineeringTests(unittest.TestCase):
    def test_app_config_reads_defaults(self):
        config = load_config({})

        self.assertEqual(config.platform_name, "Aegis Agent Platform")
        self.assertEqual(config.agent_count, 4)
        self.assertTrue(config.environment in {"development", "staging", "production"})

    def test_security_policy_enforces_rules(self):
        policy = SecurityPolicy()

        self.assertTrue(policy.is_allowed("Alina"))
        self.assertTrue(policy.is_allowed("Amin"))
        self.assertTrue(policy.is_allowed("Ahmed"))
        self.assertFalse(policy.is_allowed("UnknownAgent"))

    def test_security_policy_blocks_injection_attempts(self):
        policy = SecurityPolicy()

        with self.assertRaises(ValueError):
            policy.validate_task("SELECT * FROM users WHERE name = 'admin' OR 1=1")

    def test_health_snapshot_contains_required_fields(self):
        snapshot = health_snapshot()

        self.assertIn("service", snapshot)
        self.assertIn("status", snapshot)
        self.assertEqual(snapshot["status"], HealthStatus.HEALTHY.value)


if __name__ == "__main__":
    unittest.main()
