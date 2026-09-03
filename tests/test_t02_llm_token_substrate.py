"""T02 LLM Token Substrate tests.

Verifies:
- EchoProvider.complete returns deterministic text starting with ECHO[.
- decide_llm_model routes cheap vs expensive correctly.
- AICore.dispatch includes model + tokens; cache hit returns tokens==0.
- TokenOptimizer raises PermissionError when budget exceeded.
- No test requires a live API key or network.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from core.ai_core import AICore
from core.llm_provider import EchoProvider, get_provider
from core.model_router import TrustAwareModelRouter
from core.token_optimizer import TokenOptimizer


class TestT02LLMTokenSubstrate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        os.environ["AEGIS_DATA_DIR"] = self._tmp

    def tearDown(self):
        os.environ.pop("AEGIS_DATA_DIR", None)

    def test_echo_provider_returns_echo_text(self):
        provider = EchoProvider()
        result = provider.complete("hello world", model="aegis-cheap", max_tokens=64)
        self.assertTrue(result["text"].startswith("ECHO["))
        self.assertGreaterEqual(result["total_tokens"], 1)

    def test_get_provider_defaults_to_echo(self):
        os.environ.pop("AEGIS_LLM_PROVIDER", None)
        os.environ.pop("AEGIS_LLM_BASE_URL", None)
        os.environ.pop("AEGIS_LLM_API_KEY", None)
        provider = get_provider()
        self.assertIsInstance(provider, EchoProvider)

    def test_decide_llm_model_cheap(self):
        router = TrustAwareModelRouter()
        self.assertEqual(router.decide_llm_model("hi"), "aegis-cheap")

    def test_decide_llm_model_expensive(self):
        router = TrustAwareModelRouter()
        task = "Perform a security-review and architecture refactor of the settlement pipeline"
        self.assertEqual(router.decide_llm_model(task), "aegis-expensive")

    def test_ai_core_dispatch_includes_model_and_tokens(self):
        core = AICore()
        result = core.dispatch("ping the runtime")
        self.assertIn("model", result)
        self.assertIn("tokens", result)
        self.assertFalse(result["cached"])

    def test_ai_core_dispatch_cache_hit_tokens_zero(self):
        core = AICore()
        first = core.dispatch("ping the runtime cache test")
        second = core.dispatch("ping the runtime cache test")
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(second["tokens"], 0)

    def test_token_optimizer_budget_exceeded_raises(self):
        optimizer = TokenOptimizer(daily_budget=5)
        with self.assertRaises(PermissionError):
            optimizer.record_usage("a very long task that exceeds budget", "Alina", "x" * 200)

    def test_route_task_returns_agent_model_tier(self):
        router = TrustAwareModelRouter()
        result = router.route_task("deploy the release")
        self.assertIn("agent_name", result)
        self.assertIn("model", result)
        self.assertIn("tier", result)
        self.assertEqual(result["tier"], "cheap")


if __name__ == "__main__":
    unittest.main()
