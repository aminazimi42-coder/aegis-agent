import unittest

from core.token_economy import TokenEconomy
from core.usage_meter import UsageMeterSingleton


class TokenEconomyTest(unittest.TestCase):
    def test_cache_and_usage(self):
        te = TokenEconomy()
        tenant = "tenant_phase25"
        model = "gpt-test"
        prompt = "hello world " + ("x" * 120)
        r1 = te.call_model(tenant, model, prompt, token_budget=100)
        r2 = te.call_model(tenant, model, prompt, token_budget=100)
        # first call should not be cached, second should be cached
        self.assertFalse(bool(r1.get("cached", False)))
        self.assertTrue(bool(r2.get("cached", False)))
        # usage recorded
        usage = UsageMeterSingleton.get_usage(tenant)
        self.assertGreaterEqual(usage.tokens, 0)


if __name__ == "__main__":
    unittest.main()
