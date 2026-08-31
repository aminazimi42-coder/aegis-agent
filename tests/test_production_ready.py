import unittest

from app.api.health import readiness_check
from app.main import main
from app.services.runtime_service import RuntimeService
from core.config import load_config
from core.recovery.self_recovery import SelfRecovery
from core.runtime.runtime_context import RuntimeContext


class ProductionReadyFrameworkTests(unittest.TestCase):
    def test_runtime_context_bootstrap(self):
        config = load_config({"environment": "production", "version": "0.5.0"})
        context = RuntimeContext.from_config(config)

        self.assertEqual(context.environment, "production")
        self.assertEqual(context.agent_count, 4)
        self.assertEqual(context.version, "0.5.0")

    def test_self_recovery_reconciles_runtime_state(self):
        recovery = SelfRecovery("development", 3)
        outcome = recovery.reconcile(expected_environment="production")

        self.assertTrue(outcome["reconciled"])
        self.assertEqual(outcome["runtime"]["environment"], "production")
        self.assertEqual(outcome["runtime"]["agent_count"], 4)

    def test_readiness_check_reports_health(self):
        report = readiness_check()

        self.assertTrue(report["ready"])
        self.assertEqual(report["status"], "healthy")

    def test_runtime_service_bootstrap_runs_cleanly(self):
        config = load_config({"environment": "production", "version": "0.5.0"})
        context = RuntimeContext.from_config(config)
        service = RuntimeService(context)
        startup = service.bootstrap()

        self.assertEqual(startup["status"], "healthy")
        self.assertEqual(startup["environment"], "production")

    def test_main_entrypoint_runs_without_exception(self):
        try:
            main()
        except Exception as exc:  # pragma: no cover - guardrail for startup safety
            self.fail(f"main() raised an unexpected exception: {exc}")


if __name__ == "__main__":
    unittest.main()
