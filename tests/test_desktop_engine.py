from __future__ import annotations

import unittest

from core.desktop_engine import DesktopEngine


class TestDesktopEngine(unittest.TestCase):
    def test_run_task_returns_payload(self):
        engine = DesktopEngine()
        resp = engine.run_task("generate a short plan")
        self.assertIsInstance(resp, dict)
        self.assertIn("agent_name", resp)
        self.assertIn("response", resp)


if __name__ == "__main__":
    unittest.main()
