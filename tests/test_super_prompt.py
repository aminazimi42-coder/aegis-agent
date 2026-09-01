import unittest
from datetime import datetime, time

from core.super_prompt_engine import SuperPrompt, SuperPromptEngine


class SuperPromptTests(unittest.TestCase):
    def test_store_and_due(self):
        engine = SuperPromptEngine()
        p = SuperPrompt(
            name="weekly-report",
            prompt="Run weekly report",
            day_of_week=0,
            run_time=time(9, 0),
        )
        engine.store(p)

        # monday at 09:00
        dt = datetime(2026, 9, 7, 9, 0)
        executed = []

        def executor(prompt_text):
            executed.append(prompt_text)

        res = engine.execute_due(dt, executor)
        self.assertEqual(len(res), 1)
        self.assertEqual(executed, ["Run weekly report"])


if __name__ == "__main__":
    unittest.main()
